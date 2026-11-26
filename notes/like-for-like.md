# What moved the price: prices, and who delivered

*A note under section 16 of the methodology. Published 26 November 2026; first shown on the page for 27 November 2026.*

The daily price can move because providers changed what they charge, or because a different set of providers delivered the test that day. Section 16 of the methodology names a figure that separates the two: the change in price paid among the providers that contributed on both of two consecutive assessment days. This note defines it before it is first published, as section 16 requires. It never changes the price.

## The figure

For a day and the assessment day before it:

1. **The providers in both figures** are those that contributed on both days.
2. **The change from prices** is the change in the interquartile mean of their prices paid, from the first day to the second. It is worked out by the rule the methodology uses for the price itself (section 7): a quarter of the count, rounded down, dropped at each end, and the rest averaged. Input and output are worked out separately.
3. **The change from who delivered** is the rest of the published change: one plus the published change, divided by one plus the change from prices, less one. It covers providers that left or joined the contributors, and any shift in which providers fall in the averaged middle as a result.

The two multiply to the published change: (1 + change from prices) × (1 + change from who delivered) = (1 + published change). Each is shown as a percentage to two decimal places, halves rounded up.

## When it is shown

Only when both days have a price, the second is the next assessment day after the first, both are for the same reference model, and at least five providers contributed on both days, the floor of five that the methodology sets for a price. It is not shown on the first day after a day with no price, nor on the day the reference changes. When every part is unchanged, the day's change line already says so, and no split is shown.

In the parallel period of section 4.5 the incoming reference's figure is split in the same way, against its own figure on the day before.

## Its sources

The prices paid that each provider's row shows on the two days' pages, to four decimal places. Anyone can reproduce the figure from those two pages. Because the published price is worked out from the receipts before rounding, the split can differ from an exact one in the second decimal place; in the windows to 26 November 2026, on days when the same providers contributed on both days and so nothing but rounding separates the two, the difference was at most 0.05 per cent.

## An example

On 23 November 2026 the output price fell 3.02 per cent, from $0.7922 to $0.7683 per million tokens. Twelve providers contributed on both 20 and 23 November. The interquartile mean of their output prices paid fell from $0.8383 to $0.7683, so the change from prices was down 8.35 per cent: Crusoe had cut its price from $1.20 to $0.78. Two providers that contributed on 20 November were no longer listed on 23 November, so the change from who delivered was up 5.82 per cent. And 0.9165 × 1.0582 = 0.9698, the published fall of 3.02 per cent.

## Where it appears

On each day's page from 27 November 2026, beneath the change since the day before, and in the data files, in the columns `like_for_like_providers`, `input_change_from_prices`, `output_change_from_prices`, `input_change_from_delivery` and `output_change_from_delivery`, for every day where it can be worked out. Pages written before 27 November are never changed, so they do not show it.
