# Hunterson Standard Inference, Europe

## Methodology

Version 0.9, draft for comment, October 2026. Amended October 2026: sections 8 and 10.

This document explains, in plain language, exactly how the Hunterson Standard Inference number is produced each weekday. Anyone with the data we publish and this document should be able to reproduce the number exactly, to the published precision. If they cannot, the document is wrong and we will fix it.

The raw records behind each day's number include the venue's own responses, so they are kept privately. Every raw file is fingerprinted, and the fingerprints are published, so that any record produced later can be checked against them (section 8).

Square brackets mark details that will be settled before version 1.0.

This draft is open for comment for at least seven days. Version 1.0 will be fixed after that, and from then on every change follows section 12. Comments are welcome by email to malcolm@hunterson.org.

---

## 1. What this is

Hunterson Standard Inference, Europe is a daily price for a defined quantity of AI model output, delivered to a defined standard, and bought on the open market by a buyer in London.

It is one number, published every weekday, produced by the rules in this document and by nothing else.

It is not a recommendation, not a comparison table, and not a forecast. It is a record of what the product cost on the day.

"Europe" describes where the buyer is: a server in London, United Kingdom. It does not mean the providers are in Europe, or that the output was produced there. A provider may serve from anywhere.

## 2. Words you need

**Token.** A chunk of text, about four characters. AI models read and write in tokens, and their output is priced in tokens. A thousand tokens is roughly 750 English words.

**Input tokens** are what you send to the model. **Output tokens** are what it writes back. Output usually costs more, because the model writes one token at a time.

**Model.** The AI program itself, a very large set of numbers called weights.

**Open-weight model.** A model whose weights the maker has published for anyone to download and run. Because many companies can run the same file, there is a market with many sellers, and therefore a market price.

**Checkpoint.** One exact version of a model, identified by where it is published and a code called a commit hash. A name like "DeepSeek V4.1-Flash" can be reused or changed; a hash cannot.

**Provider.** A company that runs a model on its own computers and sells access by the token.

**Endpoint.** One offer by one provider of one model, at one stated precision and price. A provider may list more than one endpoint for the same model.

**Venue.** The marketplace where the product is bought. Ours is OpenRouter, which lists many providers' endpoints side by side and lets a buyer choose exactly which endpoint answers a request.

**Precision.** How many bits are used to store each number in the weights. A model can be shrunk to lower precision to run more cheaply, at some cost in quality. The maker publishes the weights at a stated precision, which we call **native**.

**Listed price.** The price the venue shows for an endpoint, in US dollars per million tokens, after any promotional discount open to every buyer.

**Receipt.** The cost the venue actually charges for a request, reported with the request, with the cost of input and of output stated separately.

**Price paid.** The receipt's cost of input, or of output, divided by the tokens counted. This is the price the assessment uses.

**Window.** The hour in which the product is bought: 14:00 to 15:00 UTC, Monday to Friday, except 25 December and 1 January. Every such weekday is a window, and each window is an **assessment day**.

**Census.** A copy of the venue's public listing of every model and endpoint, saved once a day, every day of the week.

**Qualifying provider.** A provider with at least one endpoint for a checkpoint at an accepted precision (section 5). A provider listing the same model twice counts once, and providers that sell from one source count once (section 5).

**Contributor.** A provider whose result enters the day's price, because it passed every test in section 7.

## 3. What is being priced

The product is one million output tokens from the reference model, served at native precision with thinking switched off, delivered fast enough to be usable, and bought through the venue from a provider that actually answered when we asked.

The full specification:

| Item | Rule |
|---|---|
| Model | The reference checkpoint named in section 4.7, identified by repository and commit hash |
| Precision | Native, as published by the model's maker and read from its `config.json` file. The accepted provider tags are listed in section 4.7 |
| Thinking | Off. Only a model whose thinking can be switched off can be the reference. A reply containing hidden "thinking" is excluded |
| Test request | A fixed, published prompt of about 7,600 input tokens. The reply is stopped at 500 output tokens |
| Venue | OpenRouter. Each request is sent to one named endpoint, with automatic fallback to any other provider switched off |
| Where from | A server in DigitalOcean's London data centre, United Kingdom |
| When | Between 14:00 and 15:00 UTC, Monday to Friday, except 25 December and 1 January. The window is set in UTC and does not move with British Summer Time |
| Speed | At least 30 output tokens per second, and the first token within 3 seconds, each taken as the median of the provider's completed requests |
| Correctness | Both check answers right, as the first two lines of every completed request, ignoring letter case |
| Completeness | The full 500 tokens, ended by the length limit |
| Price used | The price paid, taken from the receipt. The listed price for the endpoint, in force at the moment of the request, is the check: a receipt more than one per cent away from it excludes the provider that day. Promotional discounts open to every buyer are included, because they are what is paid. Volume and committed-use discounts are not included |
| Unit | US dollars per million output tokens, to four decimal places. The input price is published alongside, and a blended price at 16 input tokens to 1 output token |

## 4. Which model, and how it is chosen

### 4.1 One model at a time

Standard Inference prices exactly one model at a time, called the reference. It is not an average across models. Mixing models would mix products, and the number would stop meaning anything.

Other classes of model are, or will be, priced as separate products with their own reference. Each product has one reference.

### 4.2 The grade

Models are sorted into grades by size, using the number of **active parameters** stated on the model's own published page. Active parameters are the part of the model that does the work for each token, and they are what determines cost and speed.

Standard is the grade for models with 30 billion active parameters or fewer.

Where a model's page states two active figures, for example one while reading input and another while writing output, the larger governs.

The boundary sits in the gap between the two clusters of models found in the market, so that no model sits on the line. It is reviewed once a year, and whenever a model appears within 20 per cent of it, between 24 and 36 billion. Kimi K2.6, at 32 billion, sits inside that band, so the review is on the record from the start.

Two larger grades are tracked: Heavy, above 30 billion active parameters, and Frontier, provisionally above 70 billion. Neither is priced yet. Each launches only when it meets the rules in section 4.6.

### 4.3 The selection rule

The reference is chosen as the eligible open-weight model in the Standard grade with the most qualifying providers. It then changes only under the rules in section 4.5.

A model is **eligible** only if its thinking can be switched off. This is read each day from the venue's listing. A model that must think on every request cannot be the reference, because thinking tokens are billed as output, and would make the same job cost an unpredictable amount more from one provider to the next.

We count providers, not endpoints. A provider offering the model twice counts once. Providers that sell from one source count once (section 5).

We count every day, from the census described in section 8.

### 4.4 Why the count matters

More providers means more competition, which means the price is more likely to be a real market price and less likely to be one company's opinion.

It also means the number is harder for any one provider to move by changing its price.

### 4.5 When the reference changes

Models are replaced quickly in this market. The rules below stop the reference from jumping around, and give anyone using the number time to adjust.

**Stickiness.** The reference changes only if another eligible Standard-grade model has more qualifying providers than the reference on 20 census days in a row. A tie breaks the run. One day, or ten, is not enough.

**Before the first publication.** Nobody relies on the number yet, so the challenger becomes the reference on the twentieth day, with no parallel period and no conversion ratio.

**After the first publication:**

1. **Parallel period.** Both the old and the new reference are tested and published side by side for 30 assessment days. On each of those days we publish the ratio between the two prices.
2. **Switch.** After 30 assessment days, the new model becomes the reference. The average ratio over the period is published, so that anyone who wrote something against the old reference can convert it.
3. **Emergency.** If the old reference has fewer than five contributors on five assessment days in a row during the parallel period, the parallel period ends on its tenth assessment day, or at once if that day has passed.

**What counts as a new version.** The reference is pinned to a commit hash. If the maker changes the model's weights, or changes the chat template that wraps prompts before the model sees them, that is a new checkpoint. It is handled as a change of reference under the rules above.

Changes to documentation, evaluation results, or labels, and changes to the maker's own example code for running or loading the model, are recorded and change nothing. Providers serve the model with their own software, so that code is not part of the product.

**A new release of the same model** is a new checkpoint, not a change to the reference. It becomes the reference only by the stickiness rule. DeepSeek V4.1-Flash-1017, released on 17 October 2026, is such a challenger, and is tested alongside the reference from 19 October 2026 so that its own record of tests builds up before any change could come.

### 4.6 Launching and withdrawing a grade

A grade is first published only when both of these hold:

1. **Breadth.** On each of the last 20 census days, the model that is its reference has had at least 10 qualifying providers, and at least as many as every other eligible model in the grade. The days count whether or not the model was the reference on them.
2. **Shadow period.** The daily test has run for the grade, unpublished, until five assessment days in a row have each produced a figure, with nobody intervening in the test or the calculation.

During the shadow period each day's assessment is produced in full and kept privately. None is published, and none is changed afterwards.

Once published, a grade is withdrawn if it has fewer than five contributors on 20 assessment days in a row. It must then qualify again under this section.

These rules depend on the list of candidate models being complete. Every model seen in the census with five or more providers at one declared precision is placed in a grade, or recorded as not relevant, within ten working days.

### 4.7 The current reference

| Item | Detail |
|---|---|
| Model | DeepSeek V4.1-Flash |
| Repository | https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash |
| Commit hash | `5254448103b6254fc646dacbca1cbbf20e9216c1` |
| Name on the venue | `deepseek/deepseek-v4.1-flash` |
| Active parameters | 16 billion while writing output, 8 billion while reading input. The larger governs |
| Native precision | 8-bit floating point, with the expert layers at 4 bits, as stated in `config.json` |
| Accepted provider tag | `fp8`. Providers tagged `fp4` are excluded unless they confirm in writing that they serve the published form |
| Thinking | Can be switched off |
| Reference since | 14 October 2026 |

DeepSeek V4.1-Flash became the reference before any figure was published, when the previous candidate, GLM-5.3-Flash, was found to require thinking on every request.

## 5. Who is included

Each assessment day's panel is read from the venue's listing, saved at the start of the window. A provider is in the panel if it has at least one endpoint for the reference checkpoint at an accepted precision.

Each provider gives one observation: its endpoint with the lowest listed output price at an accepted precision. [Some providers list a lower-priority tier of the same model, such as a "flex" tier, more cheaply. Whether such a tier is the same product, or is excluded in favour of the provider's standard tier, will be settled before 1.0.]

Nobody is invited and nobody can opt out. A provider that appears on the venue at an accepted precision joins the panel that day.

Being in the panel is not enough to count. A provider contributes to the day's price only if it passes every test in section 7. The reliability test means a newcomer contributes from its ninth assessment day at the earliest.

**Precision is read from the maker's files, not from labels.** The native precision comes from the `quantization_config` field of the model's `config.json` file. Labels on the model's web page are sometimes inferred, and wrong.

**Which provider tags count.** Where a maker publishes a checkpoint in exactly one compressed format, a provider tag that names only the number of bits is treated as that format. Where a maker publishes in more than one format, only the exact tag counts.

The accepted tags for the reference are listed in section 4.7. They change only under section 12.

A provider that does not state what precision it serves is not included. A price for an unstated product is not a price.

**Independent sources, not names.** Providers that resell inference served by another listed provider or by a common network, or that are under common control, form a group and count as one provider: once among the qualifying providers, once among the contributors, and once in the price. In the price the group gives one observation: that of its member with the lowest output price paid, with that member's input price, among the members that pass every test. The other members are shown in the day's table, counted with that member.

Providers that rent computers from the same cloud, or run the same serving software, are not a group: each runs and prices its own service.

Groups are recorded on public evidence only: the provider's or network's own pages, documentation or terms, or a public record of ownership. Each group is published, with its evidence and the day it applies from, in the register `affiliations.json` in the public repository. A group applies from the census day after it is recorded and never backwards, so no published figure changes. A provider can ask for a review under section 11.

This rule was written before any case arose, because once version 1.0 is fixed a new rule needs thirty days' notice, and a rule added after it changes a result looks like moving the goalposts. Without it, one source selling under several names would add several observations and could move both the count and the price.

## 6. The daily test

Every assessment day, in the window, the London server first saves the venue's listing for the reference. It then buys the same test job from every provider in the panel, three times: in rounds starting at about 14:05, 14:20, and 14:35 UTC, in a different random order each round. Anything not reached by 14:55 UTC is recorded as not reached. Each request may take at most two minutes.

Each request is bought through the venue and sent to one named endpoint, with fallback switched off, thinking switched off, and the sampling temperature set to zero.

The request is a fixed passage of about 7,600 tokens, Act 1 Scene 2 and the opening of Act 2 Scene 1 of Shakespeare's The Tempest, with instructions to:

1. **First line: who was the rightful Duke of Milan,** which the passage establishes near its start. The expected line is `ISLAND DUKE Prospero`.
2. **Second line: who speaks the final line of the passage.** The expected line is `LAST SPEAKER Sebastian`.
3. **Then a continuous account in plain prose, until stopped.**

The prompt file is published, and its SHA-256 hash is `140afc12e0c154fd2cb843197da5d3bc673c9e1cea6e0585236b2f41a2a8b24a`. It never changes. A day on which a different prompt was sent is not an assessment day.

Only the first line differs between requests. It is a unique code, so that no provider can serve a stored copy. Any reply reporting stored (cached) input tokens is excluded. Some providers have been seen to report most of the prompt as cached even so, and to charge less for it; their replies are excluded, and the count is recorded. [Whether the test piece needs further protection against such caching will be settled before 1.0.]

We record everything, and keep it privately:

- the listing;
- the request;
- every piece of the reply, and when it arrived;
- the provider's own count of tokens;
- the cost charged;
- how the reply ended;
- which provider the venue says answered.

**The two questions are the correctness check.** If either answer is wrong, the provider did not deliver the product that day. A wrong first answer means the model did not read the prompt properly. A wrong second answer can mean the long input was cut short, or that the model was degraded.

**The prose is the length check.** It is designed to run past 500 tokens, so the reply is stopped at 500. That proves the full quantity was delivered, and lets us measure speed on the same quantity every time.

**Three tries.** Speed and first-token time are taken as the median of the provider's completed requests, so one slow moment does not disqualify a provider and one fast moment does not flatter it.

**Switching thinking off.** The request uses the venue's own switch for thinking. Some providers have been seen to ignore it and return only thinking; they are excluded on each day they do. [Whether the request should also carry the model maker's own form of the switch, so that such providers can take part, will be settled before 1.0.]

**A known limitation.** The prompt is published and sent at a fixed hour, so a provider could recognise it and give it special treatment. Buying through the venue hides who is asking, but not what is asked. We therefore also run the same test outside the window, at weekends and at a randomly chosen hour each day, and once a quarter we send an unannounced request with a different passage; we compare the speeds, and record the result. These readings are for research only and never enter the assessment.

## 7. How the number is calculated

A request is **completed** when it returns a reply with the provider's count of tokens.

For each provider in the panel, the tests below are applied in this order. The first test it fails is recorded as the reason, and the provider is excluded for the day.

1. **Listed.** It is at an accepted precision in the listing saved at the start of the window.
2. **Reliable.** It completed at least one request in at least 8 of the previous 10 windows. A window in which the test did not run, or did not finish, counts as a failure for every provider.
3. **Complete.** At least two of its three requests today completed.
4. **Correct.** Every completed request gave both correct answers as its first two lines, ignoring letter case, and was stopped by the 500-token limit.
5. **Clean.** No completed request reported thinking tokens, returned thinking text, or reported stored input tokens.
6. **Fast enough.** The median first-token time was within 3 seconds, and the median speed, measured from the first token, was at least 30 tokens per second. With two completed requests, the median is the average of the two.
7. **Same input.** Its count of input tokens was within one per cent of the median count across the panel. A different count means a different tokeniser or template, and so a different product.
8. **Receipt matches.** The receipt states the cost of input and of output separately, and the total charged was within one per cent of the listed prices multiplied by the tokens counted. The listed prices used are those in force at the moment of the request: some providers charge more at certain hours of the day, and the listing says so.

Every provider that passes all eight is a contributor. Each contributor gives its output price paid and its input price paid for the day, each the median across its completed requests. Where providers form a group (section 5), the group gives one contribution.

Then, across all contributors:

1. **Count.** If there are fewer than five, no price is published (section 9).
2. **Sort.** Sort the output prices paid from lowest to highest.
3. **Trim.** Drop a quarter of the count, rounded down, from each end.
4. **Average.** Take the average of what remains. That is the Standard Inference price.
5. **Input.** Do the same, separately, for the input prices paid.
6. **Blend.** The blended price is 16 times the input price plus the output price, divided by 17, using the results of steps 4 and 5.

The same calculation is repeated with each provider's listed discount removed, and the results are published alongside. The gap between the two shows how hard providers are discounting.

**Rounding.** Prices paid are worked out per token from the receipt, with no rounding along the way. Each result is converted to US dollars per million tokens and rounded to four decimal places, with halves rounded up.

### Worked example

Seven providers are contributors. Their output prices paid are:

0.30, 0.40, 0.45, 0.50, 0.55, 0.70, 1.50

A quarter of seven is one and three quarters, which rounds down to one. Drop the lowest one (0.30) and the highest one (1.50). Five remain:

0.40, 0.45, 0.50, 0.55, 0.70

Add them: 2.60. Divide by five: **0.5200**.

Standard Inference for the day is $0.5200 per million output tokens.

The provider at 1.50 and the provider at 0.30 both delivered the product, and both appear in the published table for the day. They simply do not move the number.

This is deliberate. One provider's promotion or premium should not move a market price.

### The blended price

Most real uses send far more input than output. The blended price weights input 16 to 1 against output, close to the shape of the test request. If the input price is 0.1200 and the output price is 0.5200:

(16 × 0.1200 + 0.5200) ÷ 17 = (1.9200 + 0.5200) ÷ 17 = 2.4400 ÷ 17 = **0.1435** per million blended tokens.

The 16 to 1 ratio is a convention, not a claim about anyone's actual usage.

### Who delivered decides the number

The price is the price paid to the providers that delivered the product in the window. It can move when providers fail to deliver, without any provider's listed price moving. In the shadow period this was seen directly: on one day the cheapest providers were slow or turned away requests together, and the figure rose by more than a quarter; the next day they delivered again and it returned.

This is the number working as intended, not an error. A price for a product that was not delivered is not a price for the product. The trim in step 3 protects against one provider's unusual price; it does not, and should not, hide a day on which much of the market failed to deliver. The table published each day shows which providers delivered and which did not, and why. [Whether any further rule is needed for such days will be settled before 1.0, in the light of the shadow period.]

## 8. Where the data comes from

**The census.** Every day, the venue's public listing of models and endpoints is saved in full, privately. Since 18 September 2026, each day's copy has been written once and never overwritten. The census is used to choose and watch the reference, to count qualifying providers, and to check eligibility. It is not the source of the price.

**The listing snapshot.** At the start of each window, the venue's listing for the reference is saved again. That copy is the day's price evidence, and the day's panel is read from it.

**Receipts.** The cost the venue charges for each request, recorded with the request. The receipt is the source of the price.

**Delivery and speed.** Our own test, described in section 6.

**The reference model's identity, size, and native precision.** The model's own published page and its `config.json` file.

**The venue.** OpenRouter. Written permission for this use was requested from its sales team on 15 October 2026 and had not been given when this draft was published. The venue's raw responses are therefore not published. [Version 1.0 will state the position on the day it is fixed.]

**What the price leaves out.** The venue charges a fee when credit is bought, and UK VAT is charged on the credit and the fee. Neither is part of the price, which is quoted per token, as prices are normally quoted. At the time of writing, the fee on a $10 purchase was $0.80, and VAT was 20 per cent.

**A check on the venue.** A control group of four providers is bought directly from their own services, rather than through the venue, in the same window and with the same test, from 20 October 2026. Its results are reported separately, and never enter the price.

**A monthly check.** Once a month we compare a sample of providers' own published prices with the venue's listing, and record any differences. A difference is not an error. The price assessed is the price paid through the venue, confirmed by the receipt.

**What we keep.** Records fall into three classes:

1. **Collected.** The census, the listing snapshots, the test records, and the readings taken outside the window. Written once, never changed, and kept permanently and privately. A SHA-256 fingerprint of every file is published each day, one file per day, and is itself written once. Anyone later shown a record can check it against its fingerprint.
2. **Derived.** The tracking and ranking pages. Rebuilt from the collected records whenever needed, with their history kept.
3. **Published.** Each day's assessment. Written once and never recalculated, even if a later method would give a different figure. Mistakes are corrected under section 11.

**Timestamps.** When a fingerprint file is written, it is sent at once to two independent timestamping services: OpenTimestamps, which records it in the Bitcoin blockchain within a few hours, and FreeTSA, a timestamp authority that signs it within seconds under the international standard RFC 3161. Only the fingerprint is sent, never the records. Both proofs are published beside the fingerprint. Together they show that the records existed, unchanged, no later than the time stamped, without anyone having to trust us or the place the files are kept.

Each day's assessment is fingerprinted and stamped in the same way when it is made, which is before it is published, with one fingerprint for each file. Until the first publication only the fingerprints and their proofs are published, so that anyone can check, once the shadow period's assessments are released, that none was changed.

A proof that cannot be obtained is requested again on the next run, and its absence is recorded. It never delays publication.

Fingerprints already published when stamping began were stamped then, and prove existence from that moment, not from the day of their records. The moment is recorded in `data/hashes/stamping-began.txt`.

How to check a fingerprint and its proofs is set out in the repository's README.

We never use another price assessment as an input.

## 9. When we do not publish

If fewer than five providers are contributors, no price is published. Instead we publish the count, the reason for each exclusion, and the words "not published".

Five is the minimum for the number to be a market price rather than a few companies' opinions.

If the test does not run, the day is marked "not published", with the reason. That day counts against every provider's reliability (section 7).

If a grade has fewer than five contributors on 20 assessment days in a row, it is withdrawn (section 4.6).

There is no assessment at weekends, on 25 December, or on 1 January.

## 10. What is published, and where

Every assessment day by 16:00 UTC, at a web address containing the grade and the date that never changes, in the form `https://hunterson.org/standard/YYYY-MM-DD/`:

- the price, the input price, and the blended price;
- the same three with discounts removed;
- the number of contributors, and the number of providers tested;
- a table of every provider tested, showing its prices paid, its listed discount, its measured speed and first-token time, and whether it was included or excluded, and why;
- the fingerprints of the day's raw records and of the day's assessment;
- the two timestamp proofs for each of those fingerprints (section 8);
- the version of this document in force that day.

Before the first publication, nothing is published: the shadow period's assessments are kept privately (section 4.6).

For the Heavy and Frontier grades, which are not yet priced, we publish the daily count of qualifying providers for each grade's reference, and the reason no price is given.

The full history is available as a single downloadable file, with a column for the grade.

A published page is never changed. See section 11.

## 11. Mistakes and complaints

If we discover an error in a published number, we do not change the page. We publish a correction on a new page, dated, stating what was wrong, what the correct figure is, and why it happened.

Where a correction exists, a notice linking to it is shown with the original page, drawn from the list of corrections. The original page itself stays as published.

Errors we find ourselves and errors reported to us are treated the same way.

**Complaints.** Anyone may complain about a published figure, or about how these rules have been applied, by email to malcolm@hunterson.org. We acknowledge a complaint within five working days, and reply in writing within twenty. Where a complaint leads to a correction, the outcome is published with it.

## 12. Changing these rules

Any change to this document is announced at least 30 days before it takes effect, with the reason. During those 30 days anyone can comment. The change, the comments, and the response are published.

This includes the accepted provider tags in section 4.7, because changing them changes who is in the panel.

Each version of this document is numbered and kept. The version in force on any day is recorded on that day's page.

A change of reference model follows section 4.5 and is not a change to these rules.

## 13. Using the numbers

The published prices, the history, and the daily tables are released under the Creative Commons Attribution 4.0 licence. Anyone may use, copy, quote, or build on them, for any purpose, provided they credit Hunterson.

The fingerprints are released under the same licence.

The raw records, meaning the census, the listing snapshots, and the test records, include the venue's own responses. They remain OpenRouter's material, under its terms. They are kept privately, and are neither published nor licensed by us.

This document is released under the same Creative Commons licence.

## 14. Who produces this, and what they own

Hunterson Standard Inference is produced by Malcolm Hunter (a pen name), trading as Hunterson, in the United Kingdom.

The producer holds no shares, tokens, or other interest in any provider tested, in any company that makes a model tested, in any GPU cloud or listed inference provider, in compute futures, or in any financial product whose value depends on this number.

The producer holds no tokens of, and accepts no payment, airdrop, or advisory role from, any network that sells AI inference or GPU compute.

Holdings through broadly diversified funds and pensions, where the producer does not choose the investments, are excepted. Holdings unrelated to this sector are not listed.

The producer accepts no payment from any provider or model maker. This statement is updated whenever it changes, and the date of the last change is shown.

## 15. Who can change the number

Nobody can change a day's number. It is produced by the published rules from the published data. There is no panel, no override, and no discretion over any day's figure.

Three kinds of decision do involve judgement:

1. **Placing a model in a grade,** under section 4.2.
2. **Deciding which provider tags count as a model's native form,** under section 5.
3. **Recording that providers form a group,** under section 5, on public evidence only.

All three are recorded, with the reasons, in the public selection record or the published register before they take effect: https://github.com/Hunterson42/Hunterson/blob/main/notes/selection.md and https://github.com/Hunterson42/Hunterson/blob/main/affiliations.json. All can be challenged under section 11.

If the rules produce a number that looks wrong, the right response is to check the data and, if the rules are at fault, to change them through section 12.

## 16. Figures published alongside

These are published with the daily price, and never change it:

1. **The price without discounts,** and the gap between the two (section 7).
2. **The control group:** the same test bought directly from providers' own services, set beside the venue's result for the same providers (section 8).
3. **Provider counts for grades not yet priced** (section 10).

Further figures are planned from January 2027, once a month of history exists, such as the output a graphics processor must deliver each hour to cover its rental at the assessed price. Each will be defined in a published note, with its sources, before it is first published.

## 17. Standards followed

These rules are written to follow the IOSCO Principles for Oil Price Reporting Agencies, adapted to a product that is bought and timed rather than traded.

[Version 1.0 will set out, principle by principle, how each is met.]

## 18. What this number is not

It is not the price large buyers actually pay. Large customers negotiate discounts that are not public. This number is built from prices actually paid, by buying the product and keeping the receipt, checked against the listed price. It does not see private deals.

It is not a price for closed models. Models like Claude, GPT, or Gemini each come from a single maker, and are sold only where that maker allows, so they have a list price but not a market price. Their listed prices are recorded separately as context, and never enter this number.

It is not a quality rating. Two providers serving the same checkpoint at native precision are treated as delivering the same product. Differences in speed above the floor, or in reliability above the threshold, are published in the daily table but do not affect the price.

It is not a list price. It moves with who delivered on the day, as well as with what they charged (section 7).

It is not a price for output produced in Europe. See section 1.

## 19. Version history

| Version | Date | Change |
|---|---|---|
| 0.9 | October 2026 | Draft published for comment |
| 0.9, amended | October 2026 | Sections 8 and 10: timestamps built, settling the square bracket in section 10 |

---

Questions, complaints, and reports of errors: malcolm@hunterson.org
