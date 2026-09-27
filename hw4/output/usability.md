# Problem 9 usability changes

## 1. Product search and filters

The Products page now searches product names and filters by garment type, size, and stock availability. The availability filter evaluates the selected size when a size is chosen, or the product's full inventory otherwise. This narrows the catalogue to items a shopper can use and shows the result count. Clear filters restores the full catalogue.

## 2. Recently viewed products

Opening a product detail page records it in browser local storage. The Products page shows the six most recently viewed items above the full results. This gives shoppers a quick path back to items they were considering without changing their account or server history.

## 3. Stock-aware chat recommendations

The agent searches the database catalogue and returns candidate IDs. The backend applies explicit size, color, and budget constraints to those candidates using canonical database prices, colors, and inventory. A requested size must have positive stock. Product cards are re-resolved from the catalogue, and constrained replies are generated from the verified matches so an out-of-stock or over-budget item is not shown as a match.

## 4. Side-by-side product comparison

For a comparison request, the agent identifies two products through the catalogue tools. When the shopper names only a category, the backend can select two matching, in-stock catalogue products rather than returning a dead-end clarification. The backend resolves prices, colors, and currently available sizes from SQLite and returns those fields as structured comparison data. Chat displays both products side by side with links to their existing detail pages. Comparison data is stored alongside the assistant turn, so it can be restored with signed-in chat history while older saved card lists remain readable.
