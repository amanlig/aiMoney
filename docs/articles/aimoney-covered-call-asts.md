# aiMoney: Making Covered-Call Decisions Easier to Understand

*An ASTS walkthrough · October 26, 2026*

Selling a covered call starts with a straightforward exchange: receive a premium in return for accepting an obligation to sell shares at a specified strike price if assigned. Managing that position over time creates a harder question: what should I do next?

Keep the existing position? Close it and release cash? Buy back the call and sell another at a different strike or expiration?

I built **aiMoney**, a covered-call scenario analytics tool for comparing those choices. Its covered-call optimizer brings stock holdings, option quotes, purchase costs and scenario calculations into one visual workspace. The goal is to make the cash flows and assumptions easier to inspect before making a decision.

## The problem: a premium tells only part of the story

A replacement call can offer an attractive premium, but collecting that premium may first require an expensive buyback of the existing call. A rollover that brings in cash also extends an obligation; it does not automatically establish an overall profit.

The practical questions are connected: how much would closing release today, how much cash would a rollover require, and what would the resulting position look like under different stock-price assumptions?

aiMoney puts those questions side by side rather than leaving the trader to assemble the comparison from separate quotes and spreadsheets.

## ASTS: walking through an existing position

The example below uses the saved ASTS position already in the application: **500 shares covered by five $40 calls expiring January 21, 2028**. Its saved stock quote is approximately **US$41.06 per share**.

These are historical inputs from the October 21 capture, not today's prices or a recommendation to trade ASTS. The screenshot was saved during UI verification on October 23. Its first rollover is switched to **Expire**, while the other two remain in **Close** mode, illustrating the difference between the two views.

**Read the profit bars with this limitation in mind:** the chart includes the recorded premium for the latest call sale but does not include transactions from previous rollovers. Its displayed profit is therefore incomplete as a measure of the position's lifetime performance and cannot reconcile the account balance. Fees are also excluded. In Expire mode, the purple bar shows option-only P&L and excludes the value of retained shares; it is not directly comparable with full-position Close profit.

![aiMoney covered-call optimizer showing the saved ASTS position, a stock-price scenario slider, a Close today reference and three rollover alternatives.](assets/aimoney-asts-ui-2026-10-23.png)

*Actual application UI, captured October 23, 2026, using October 21 saved quotes. Displayed profit excludes prior rollover history; values are scenario outputs, not verified cumulative returns.*

Start with **Close today**. At the saved quotes, selling 500 shares at the US$41.01 bid would generate US$20,505. Buying back five calls at the US$16.65 ask would cost US$8,325. The difference is **US$12,180 of closing cash before fees**. That is cash released by closing the position—not profit earned over its history.

Next, inspect the rollover alternatives. The saved screen includes $45 and $50 replacement strikes with different expirations. Each requires buying back the existing call and selling a replacement. The **Roll cash needed** indicator shows the estimated opening shortfall when the buyback costs more than the new premium brings in. It is separate from the broker's margin or buying-power requirement.

Finally, move the stock-price slider. This changes the hypothetical starting stock price used for rollover scenarios while preserving Close today as a fixed reference at captured quotes. It makes the sensitivity of the alternatives visible without suggesting that a particular future stock price is certain.

## What the solution entails

The application combines saved transaction inputs with Questrade stock and option quotes and Yahoo stock-price history. The optimizer samples historical returns to construct stock-price scenarios, estimates option values under fixed volatility and spread assumptions, and presents three ranked rollover candidates.

In **Close** mode, it models liquidation at a 30-trading-day review horizon, including expiration and assignment handling when applicable. In **Expire** mode, it instead shows a conditional case in which the replacement call expires worthless and the shares remain held. Selecting Expire does not mean the model predicts that outcome, and it does not change the Close-based candidate ranking.

The chart separates stock proceeds, call buyback costs, replacement premiums and the applicable profit measure. The application also includes an AI-powered recommendation feature to help interpret the comparison. The application does not place orders.

## From the chart to a recommendation

The **Recommendation** panel lets the trader choose an objective: **Prefer retaining stock**, **Free cash for another investment**, or **Compare alternatives**. Selecting **Generate recommendation** sends a snapshot of the selected holding, stock-price scenario, Close / Expire choices and calculated cash flows to OpenAI for a conditional assessment.

For ASTS, that means asking how closing the existing position compares with the displayed rollover contracts given the selected objective. Someone who wants to retain the shares is asking a different question from someone who wants to release cash for another investment. The recommendation discusses the alternatives and their cash requirements in that context.

Pricing, scenario calculations and candidate ranking come from the application's model. The AI interprets those results; choosing an objective does not re-rank the chart. Successful assessments and their input snapshots are saved in the application database for later review. If the chart inputs change, generate a new recommendation to assess the updated scenario.

The assessment receives neither live news nor the account's available cash balance. It also inherits the chart's missing prior rollover history. It can help explain the trade-offs, but it cannot establish full historical profit, confirm affordability or determine whether market conditions are healthy.

## Where the app stands today

aiMoney is a working decision-support tool with further accounting work to do. The missing rollover history is a concrete example: a complete performance view needs every linked premium, buyback cost and fee counted once across the position's life.

The scenario model also holds volatility and spreads fixed, excludes fees and taxes, and does not simulate early assignment. Its historical option-pricing accuracy has not been established through backtesting. These boundaries matter when interpreting the rankings and chart amounts.

The useful question today is: **under these inputs and assumptions, how do the alternatives differ?** Full account-performance reconciliation remains outside the current chart's capabilities.

## How to get access

The application is available at **[aimoney.kodekomplete.com](https://aimoney.kodekomplete.com)**. Access is currently by invitation: contact the app owner to have your email address authorized. There is no public registration form.

Once authorized, enter your email on the sign-in page and use the eight-digit code sent to your inbox. No separate aiMoney password is required; codes expire after ten minutes.

The current version uses a shared portfolio workspace for authorized users. Separate private portfolios and role-based permissions are future work, so access should be arranged with that shared workspace in mind.

For the ASTS example, aiMoney makes the next decision easier to examine: what cash would closing release, what would a rollover cost, and which assumptions drive the comparison? That visibility is the purpose of the app—and making the limitations visible is part of the same job.
