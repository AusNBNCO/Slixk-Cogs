import random 
import discord 
from discord.ui import View, button 
from redbot.core import commands, bank

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

    def _format_hand(self, hand):
        return ', '.join(f"{rank} of {suit}" for rank, suit in hand)

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
            value=f"{self._format_cards(player_hand)}
**Score:** {player_total}",
            inline=False
        )

        embed.add_field(
            name="Dealer's Visible Card",
            value=f"{dealer_hand[0][0]} {self._format_cards([dealer_hand[0]])[-1].split()[-1]}",
            inline=False
        )

        await ctx.send(embed=embed, view=BlackjackView(ctx, self))


    @commands.command(name="topcredits", aliases=["leaderboard", "topbal"])
    async def top_credits(self, ctx):
        """Show the top users with the most credits in the server."""
        guild = ctx.guild
        members = [m for m in guild.members if not m.bot]
        balances = []

        for member in members:
            try:
                bal = await bank.get_balance(member)
                balances.append((member, bal))
            except:
                continue

        top = sorted(balances, key=lambda x: x[1], reverse=True)[:10]
        if not top:
            await ctx.send("Nobody has credits yet.")
            return

        medals = ["🥇", "🥈", "🥉"]
        desc = ""
        for i, (user, bal) in enumerate(top):
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            desc += f"{medal} **{user.display_name}** — `{bal}` credits\n""

        embed = discord.Embed(
            title="💰 Server Credit Leaderboard",
            description=desc,
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

class SplitState:
    def __init__(self, hand1, hand2):
        self.hands = [hand1, hand2]
        self.current = 0

    def current_hand(self):
        return self.hands[self.current]

    def advance(self):
        self.current += 1
        return self.current < len(self.hands)

class BlackjackView(View):
    def __init__(self, ctx, cog, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog
        self.split_state = None

    @button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, action="hit")

    @button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, action="stand")

    @button(label="Split", style=discord.ButtonStyle.danger)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, action="split")

    @button(label="Double", style=discord.ButtonStyle.success)
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_action(interaction, action="double")

    async def handle_action(self, interaction, action):
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

        player_hand = (
            self.split_state.current_hand()
            if self.split_state
            else game["player"]
        )

        msg = ""
        if self.split_state:
            msg += f"**Now playing hand {self.split_state.current + 1} of {len(self.split_state.hands)}**\n"

        if action == "split":
            if len(player_hand) == 2 and player_hand[0][0] == player_hand[1][0]:
                if not await bank.can_spend(interaction.user, bet):
                    await interaction.response.send_message("Not enough credits to split.", ephemeral=True)
                    return
                await bank.withdraw_credits(interaction.user, bet)
                hand1 = [player_hand[0], deck.pop()]
                hand2 = [player_hand[1], deck.pop()]
                self.split_state = SplitState(hand1, hand2)
                msg += f"**Split!** Now playing hand 1 of 2: {self.cog._format_cards(hand1)}"
                await interaction.response.edit_message(content=msg, view=self)
                return
            else:
                await interaction.response.send_message("You can only split matching cards on the first move.", ephemeral=True)
                return

        if action == "hit":
            card = deck.pop()
            player_hand.append(card)
            total = self.cog._hand_value(player_hand)
            msg += f"You drew **{card[0]} of {card[1]}**.\n"
            if total >= 21:
                action = "stand"

        elif action == "double":
            if not await bank.can_spend(interaction.user, bet):
                await interaction.response.send_message("Not enough credits to double down.", ephemeral=True)
                return
            await bank.withdraw_credits(interaction.user, bet)
            game["bet"] = bet * 2
            card = deck.pop()
            player_hand.append(card)
            msg += f"**Double Down!** You drew **{card[0]} of {card[1]}**.\n"
            action = "stand"

        if action == "stand":
            if self.split_state:
                if self.split_state.advance():
                    await interaction.response.edit_message(content=f"Moving to hand {self.split_state.current + 1}", view=self)
                    return

                # Evaluate both hands
                total_winnings = 0
                split_result_text = ""
                dealer_total = self.cog._hand_value(dealer_hand)
                while dealer_total < 17:
                    card = deck.pop()
                    dealer_hand.append(card)
                    dealer_total = self.cog._hand_value(dealer_hand)

                for i, hand in enumerate(self.split_state.hands):
                    score = self.cog._hand_value(hand)
                    result = ""
                    hand_payout = 0
                    if score > 21:
                        result = "Bust"
                    elif dealer_total > 21 or score > dealer_total:
                        result = "Win"
                        hand_payout = bet * 2
                        total_winnings += hand_payout
                        await bank.deposit_credits(interaction.user, hand_payout)
                    elif dealer_total == score:
                        result = "Push"
                        total_winnings += bet
                        await bank.deposit_credits(interaction.user, bet)
                    else:
                        result = "Lose"
                    split_result_text += f"**Hand {i+1}:** {self.cog._format_cards(hand)} (Score: {score}) — **{result}**\n"

                embed = discord.Embed(
                    title="🃏 Blackjack — Split Results",
                    description=split_result_text,
                    color=discord.Color.green() if total_winnings else discord.Color.red()
                )
                embed.add_field(
                    name="Dealer's Hand",
                    value=f"{self.cog._format_cards(dealer_hand)} (Score: {dealer_total})",
                    inline=False
                )
                embed.add_field(
                    name="Total Winnings",
                    value=f"`{total_winnings}` credits" if total_winnings else "You lost both hands.",
                    inline=False
                )
                balance = await bank.get_balance(interaction.user)
                embed.set_footer(text=f"Remaining Balance: {balance} credits")
                self.cog.bj_games.pop(interaction.user.id, None)
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(content=None, embed=embed, view=self)
                self.stop()
                return

            # Normal game resolution (no split)
            player_total = self.cog._hand_value(player_hand)
            dealer_total = self.cog._hand_value(dealer_hand)
            while dealer_total < 17:
                card = deck.pop()
                dealer_hand.append(card)
                dealer_total = self.cog._hand_value(dealer_hand)

            payout = 0
            result = "House Wins!"
            if dealer_total > 21 or player_total > dealer_total:
                payout = game["bet"] * 2
                result = "You Win!"
                await bank.deposit_credits(interaction.user, payout)
            elif dealer_total == player_total:
                result = "Push!"
                await bank.deposit_credits(interaction.user, game["bet"])

            embed = discord.Embed(
                title="Slixk's 🎲 Casino | Blackjack",
                color=discord.Color.green()
            )
            embed.add_field(
                name=f"__{interaction.user.display_name}'s Hand__",
                value=f"{self.cog._format_cards(player_hand)}\n**Score:** {player_total}",
                inline=False
            )
            embed.add_field(
                name="Dealer's Hand",
                value=f"{self.cog._format_cards(dealer_hand)}\n**Score:** {dealer_total}",
                inline=False
            )
            embed.add_field(
                name="**Outcome:**",
                value=f"**{result}**",
                inline=False
            )
            embed.add_field(
                name="​",
                value="You won `{}` credits!".format(payout) if payout else "Sorry, you didn't win anything." if result != "Push!" else "Your bet was returned.",
                inline=False
            )
            balance = await bank.get_balance(interaction.user)
            embed.set_footer(text=f"Remaining Balance: {balance} credits")
            self.cog.bj_games.pop(interaction.user.id, None)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=None, embed=embed, view=self)
            self.stop()
            return

        total = self.cog._hand_value(player_hand)
        msg += f"**Your hand:** {self.cog._format_cards(player_hand)} (Total: {total})\n"
        msg += "Choose to Hit, Stand, Split or Double."
        await interaction.response.edit_message(content=msg, view=self)

async def setup(bot): 
    await bot.add_cog(Casino(bot))
