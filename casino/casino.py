import random
import discord
from discord.ui import View, button
from redbot.core import commands, bank  # type: ignore

MIN_BET = 500

class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bj_games = {}

    def _new_deck(self):
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [(rank, suit) for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def _format_cards(self, hand):
        suit_emojis = {
            'Spades': '♠️',
            'Hearts': '♥️',
            'Diamonds': '♦️',
            'Clubs': '♣️',
        }
        return ', '.join(f"{rank} {suit_emojis.get(suit, '?')}" for rank, suit in hand)

    def _hand_value(self, hand):
        total = 0
        aces = 0
        for rank, _ in hand:
            if rank in ['J', 'Q', 'K']:
                total += 10
            elif rank == 'A':
                total += 11
                aces += 1
            else:
                total += int(rank)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    @commands.command(name="bj")
    async def blackjack_start(self, ctx, bet: int):
        user = ctx.author
        if bet < MIN_BET:
            await ctx.send(f"The minimum bet is {MIN_BET} credits.")
            return
        if not await bank.can_spend(user, bet):
            await ctx.send("You do not have enough credits for that bet.")
            return
        if user.id in self.bj_games:
            await ctx.send("You already have an active Blackjack game.")
            return

        await bank.withdraw_credits(user, bet)
        deck = self._new_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        self.bj_games[user.id] = {
            "bet": bet,
            "deck": deck,
            "player": player_hand,
            "dealer": dealer_hand,
        }
        player_total = self._hand_value(player_hand)
        embed = discord.Embed(
            title="Slixk's 🎲 Casino | Blackjack",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name=f"__{ctx.author.display_name}'s Hand__",
            value=f"{self._format_cards(player_hand)}**Score:** {player_total}",
            inline=False
        )
        embed.add_field(
            name="Dealer's Visible Card",
            value=f"{self._format_cards([dealer_hand[0]])}",
            inline=False
        )
        await ctx.send(embed=embed, view=BlackjackView(ctx, self))

class BlackjackView(View):
    def __init__(self, ctx, cog, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog

    @button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "hit")

    @button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "stand")

    @button(label="Double", style=discord.ButtonStyle.success)
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, "double")

    async def handle_action(self, interaction: discord.Interaction, action: str):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        game = self.cog.bj_games.get(interaction.user.id)
        if not game:
            await interaction.response.send_message("No active game found.", ephemeral=True)
            self.stop()
            return

        deck = game["deck"]
        bet = game["bet"]
        dealer_hand = game["dealer"]
        player_hand = game["player"]

        if action == "hit":
            card = deck.pop()
            player_hand.append(card)
            total = self.cog._hand_value(player_hand)
            if total >= 21:
                await self.handle_action(interaction, "stand")
                return
            embed = discord.Embed(
                title="Slixk's 🎲 Casino | Blackjack",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name=f"__{interaction.user.display_name}'s Hand__",
                value=f"{self.cog._format_cards(player_hand)}**Score:** {total}",
                inline=False
            )
            embed.add_field(
                name="Dealer's Visible Card",
                value=f"{self.cog._format_cards([dealer_hand[0]])}",
                inline=False
            )
            await interaction.response.edit_message(content=None, embed=embed, view=self)
            return

        elif action == "double":
            if not await bank.can_spend(interaction.user, bet):
                await interaction.response.send_message("Not enough credits to double down.", ephemeral=True)
                return
            await bank.withdraw_credits(interaction.user, bet)
            game["bet"] = bet * 2
            card = deck.pop()
            player_hand.append(card)
            player_total = self.cog._hand_value(player_hand)

            dealer_total = self.cog._hand_value(dealer_hand)
            while dealer_total < 17:
                dealer_hand.append(deck.pop())
                dealer_total = self.cog._hand_value(dealer_hand)

            payout = 0
            result = "House Wins!"
            if player_total > 21:
                result = "Bust!"
            elif dealer_total > 21 or player_total > dealer_total:
                payout = game["bet"]
                result = "You Win!"
                await bank.deposit_credits(interaction.user, payout * 2)
            elif dealer_total == player_total:
                result = "Push!"
                await bank.deposit_credits(interaction.user, bet)

            embed = discord.Embed(
                title="Slixk's 🎲 Casino | Blackjack (Double Down)",
                color=discord.Color.green() if payout else discord.Color.red()
            )
            embed.add_field(
                name=f"__{interaction.user.display_name}'s Hand__",
                value=f"{self.cog._format_cards(player_hand)}**Score:** {player_total}",
                inline=False
            )
            embed.add_field(
                name="Dealer's Hand",
                value=f"{self.cog._format_cards(dealer_hand)}**Score:** {dealer_total}",
                inline=False
            )
            embed.add_field(name="**Outcome:**", value=f"**{result}**", inline=False)
            balance = await bank.get_balance(interaction.user)
            embed.set_footer(text=f"Remaining Balance: {balance} credits")

            self.cog.bj_games.pop(interaction.user.id, None)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=None, embed=embed, view=self)
            self.stop()
            return

        elif action == "stand":
            player_total = self.cog._hand_value(player_hand)
            dealer_total = self.cog._hand_value(dealer_hand)
            while dealer_total < 17:
                dealer_hand.append(deck.pop())
                dealer_total = self.cog._hand_value(dealer_hand)

            payout = 0
            result = "House Wins!"
            if dealer_total > 21 or player_total > dealer_total:
                payout = game["bet"]
                result = "You Win!"
                await bank.deposit_credits(interaction.user, payout * 2)
            elif dealer_total == player_total:
                result = "Push!"
                await bank.deposit_credits(interaction.user, game["bet"])

            embed = discord.Embed(
                title="Slixk's 🎲 Casino | Blackjack",
                color=discord.Color.green() if payout else discord.Color.red()
            )
            embed.add_field(
                name=f"__{interaction.user.display_name}'s Hand__",
                value=f"{self.cog._format_cards(player_hand)}**Score:** {player_total}",
                inline=False
            )
            embed.add_field(
                name="Dealer's Hand",
                value=f"{self.cog._format_cards(dealer_hand)}**Score:** {dealer_total}",
                inline=False
            )
            embed.add_field(name="**Outcome:**", value=f"**{result}**", inline=False)
            balance = await bank.get_balance(interaction.user)
            embed.set_footer(text=f"Remaining Balance: {balance} credits")

            self.cog.bj_games.pop(interaction.user.id, None)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=None, embed=embed, view=self)
            self.stop()

async def setup(bot):
    await bot.add_cog(Casino(bot))