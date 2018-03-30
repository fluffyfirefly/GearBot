import asyncio
import datetime
import time
import traceback

import discord
from discord.ext import commands
from discord.ext.commands import BadArgument

from Util import Permissioncheckers, Configuration, Util, GearbotLogging
from Util.Converters import BannedMember


class Moderation:

    def __init__(self, bot):
        self.bot:commands.Bot = bot
        self.mutes = Util.fetchFromDisk("mutes")
        self.running = True
        self.bot.loop.create_task(unmuteTask(self))

    def __unload(self):
        Util.saveToDisk("mutes", self.mutes)
        self.running = False

    async def __local_check(self, ctx):
        return Permissioncheckers.isServerMod(ctx)

    @commands.command()
    @commands.guild_only()
    async def roles(selfs, ctx:commands.Context):
        """Lists all roles on the server and their IDs, usefull for configuring without having to ping that role"""
        roles = ""
        ids = ""
        for role in ctx.guild.roles:
            roles += f"<@&{role.id}>\n\n"
            ids += str(role.id) + "\n\n"
        embed = discord.Embed(title=ctx.guild.name + " roles", color=0x54d5ff)
        embed.add_field(name="\u200b", value=roles, inline=True)
        embed.add_field(name="\u200b", value=ids, inline=True)
        await ctx.send(ctx.channel, embed=embed)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, user: discord.User, *, reason="No reason given."):
        """Kicks an user from the server."""
        await ctx.guild.kick(user, reason=f"Moderator: {ctx.author.name} ({ctx.author.id}) Reason: {reason}")
        await ctx.send(f":ok_hand: {user.name} ({user.id}) was kicked. Reason: `{reason}`")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx:commands.Context, user: discord.Member, *, reason="No reason given"):
        """Bans an user from the server."""
        if (ctx.author != user and user != ctx.bot.user and ctx.author.top_role > user.top_role) or await ctx.bot.is_owner(ctx.author):
            await ctx.guild.ban(user, reason=f"Moderator: {ctx.author.name} ({ctx.author.id}) Reason: {reason}")
            await ctx.send(f":ok_hand: {user.name} ({user.id}) was banned. Reason: `{reason}`")
        else:
            await ctx.send(f":no_entry: You are not allowed to ban {user.name}")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    async def forceban(self, ctx:commands.Context, user_id: int, *, reason="No reason given"):
        """Bans a user even if they are not in the server"""
        try:
            member = await commands.MemberConverter().convert(ctx, str(user_id))
        except BadArgument:
            user = await ctx.bot.get_user_info(user_id)
            if user == ctx.author or user == ctx.bot.user:
                await ctx.send("You cannot ban that user!")
            else:
                await ctx.guild.ban(user, reason=f"Moderator: {ctx.author.name} ({ctx.author.id}) Reason: {reason}")
                await ctx.send(f":ok_hand: {user.name} ({user.id}) was banned. Reason: `{reason}`")
        else:
            await ctx.send(f":warning: {member.name} is on this server, executing regular ban command instead")
            await ctx.invoke(self.ban, member, reason=reason)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, member: BannedMember, *, reason="No reason given"):
        """Unbans an user from the server."""
        await ctx.guild.unban(member.user, reason=f"Moderator: {ctx.author.name} ({ctx.author.id}) Reason: {reason}")
        await ctx.send(f":ok_hand: {member.user.name} ({member.user.id}) has been unbanned. Reason: `{reason}`")
        # This should work even if the user isn't cached


    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def mute(self, ctx:commands.Context, target:discord.Member, durationNumber:int, durationIdentifier:str, *, reason="No reason provided"):
        """Temporary mutes someone"""
        roleid = Configuration.getConfigVar(ctx.guild.id, "MUTE_ROLE")
        if roleid is 0:
            await ctx.send(f":warning: Unable to comply, you have not told me what role i can use to mute people, but i can still kick {target.mention} if you want while a server admin tells me what role i can use")
        else:
            role = discord.utils.get(ctx.guild.roles, id=roleid)
            if role is None:
                await ctx.send(f":warning: Unable to comply, someone has removed the role i was told to use, but i can still kick {target.mention} while a server admin makes a new role for me to use")
            else:
                duration = Util.convertToSeconds(durationNumber, durationIdentifier)
                until = time.time() + duration
                await target.add_roles(role, reason=f"{reason}, as requested by {ctx.author.name}")
                if not str(ctx.guild.id) in self.mutes:
                    self.mutes[str(ctx.guild.id)] = dict()
                self.mutes[str(ctx.guild.id)][str(target.id)] = until
                await ctx.send(f"{target.display_name} has been muted")
                Util.saveToDisk("mutes", self.mutes)
                modlog = ctx.guild.get_channel(Configuration.getConfigVar(ctx.guild.id, "MOD_LOGS"))
                if modlog is not None:
                    await modlog.send(f":zipper_mouth: {target.name}#{target.discriminator} (`{target.id}`) has been muted by {ctx.author.name} for {durationNumber} {durationIdentifier}: {reason}")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx:commands.Context, target:discord.Member, *, reason="No reason provided"):
        roleid = Configuration.getConfigVar(ctx.guild.id, "MUTE_ROLE")
        if roleid is 0:
            await ctx.send(f"The mute feature has been dissabled on this server, as such i cannot unmute that person")
        else:
            role = discord.utils.get(ctx.guild.roles, id=roleid)
            if role is None:
                await ctx.send(f":warning: Unable to comply, the role i've been told to use for muting no longer exists")
            else:
                await target.remove_roles(role, reason=f"Unmuted by {ctx.author.name}, {reason}")
                await ctx.send(f"{target.display_name} has been unmuted")
                modlog = ctx.guild.get_channel(Configuration.getConfigVar(ctx.guild.id, "MOD_LOGS"))
                if modlog is not None:
                    await modlog.send(
                        f":innocent: {target.name}#{target.discriminator} (`{target.id}`) has been unmuted by {ctx.author.name}")


    async def on_guild_channel_create(self, channel:discord.abc.GuildChannel):
        guild:discord.Guild = channel.guild
        roleid = Configuration.getConfigVar(guild.id, "MUTE_ROLE")
        if roleid is not 0:
            role = discord.utils.get(guild.roles, id=roleid)
            if role is not None:
                if isinstance(channel, discord.TextChannel):
                    await channel.set_permissions(role, reason="Automatic mute role setup", send_messages=False, add_reactions=False)
                else:
                    await channel.set_permissions(role, reason="Automatic mute role setup", speak=False, connect=False)

    async def on_member_join(self, member: discord.Member):
        while not self.bot.STARTUP_COMPLETE:
            await asyncio.sleep(1)
        if member.id in self.mutes[str(member.guild.id)]:
            roleid = Configuration.getConfigVar(member.guild.id, "MUTE_ROLE")
            if roleid is not 0:
                role = discord.utils.get(member.guild.roles, id=roleid)
                if role is not None:
                    await member.add_roles(role, reason="Member left and re-joined before mute expired")
                    modlog = member.guild.get_channel(Configuration.getConfigVar(member.guild.id, "MOD_LOGS"))
                    if modlog is not None:
                        await modlog.send(f":zipper_mouth: {member.name}#{member.discriminator} (`{member.id}`) has re-joined the server before his mute expired has has been muted again")

def setup(bot):
    bot.add_cog(Moderation(bot))

async def unmuteTask(modcog:Moderation):
    while not modcog.bot.STARTUP_COMPLETE:
        await asyncio.sleep(1)
    GearbotLogging.info("Started unmute background task")
    skips = []
    updated = False
    while modcog.running:
        try:
            guildstoremove = []
            for guildid, list in modcog.mutes.items():
                guild:discord.Guild = modcog.bot.get_guild(int(guildid))
                toremove = []
                if Configuration.getConfigVar(int(guildid), "MUTE_ROLE") is 0:
                    guildstoremove.append(guildid)
                for userid, until in list.items():
                    if time.time() > until and userid not in skips:
                        member = guild.get_member(int(userid))
                        role = discord.utils.get(guild.roles, id=Configuration.getConfigVar(int(guildid), "MUTE_ROLE"))
                        modlog = guild.get_channel(Configuration.getConfigVar(int(guildid), "MOD_LOGS"))
                        await member.remove_roles(role, reason="Mute expired")
                        if modlog is not None:
                            await modlog.send(f":innocent: {member.name}#{member.discriminator} (`{member.id}`) has automaticaly been unmuted")
                        updated = True
                        toremove.append(userid)
                for todo in toremove:
                    del list[todo]
                await asyncio.sleep(0)
            if updated:
                Util.saveToDisk("mutes", modcog.mutes)
                updated = False
            for id in guildstoremove:
                del modcog.mutes[id]
            await asyncio.sleep(10)
        except Exception as ex:
            GearbotLogging.exception("Something went wrong in the unmute task", ex)
            skips.append(userid)
            embed = discord.Embed(colour=discord.Colour(0xff0000),
                                  timestamp=datetime.datetime.utcfromtimestamp(time.time()))

            embed.set_author(name="Something went wrong in the unmute task:")
            embed.add_field(name="Current guildid", value=guildid)
            embed.add_field(name="Current userid", value=userid)
            embed.add_field(name="Exception", value=ex)
            v = ""
            for line in traceback.format_exc().splitlines():
                if len(v) + len(line) > 1024:
                    embed.add_field(name="Stacktrace", value=v)
                    v = ""
                v = f"{v}\n{line}"
            if len(v) > 0:
                embed.add_field(name="Stacktrace", value=v)
            await GearbotLogging.logToBotlog(embed=embed)
            await asyncio.sleep(10)
    GearbotLogging.info("Unmute background task terminated")
