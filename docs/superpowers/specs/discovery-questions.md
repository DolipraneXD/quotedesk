# Quotation System — Client Discovery Questions

**Purpose:** surface the expensive surprises *before* writing code.
**How to use:** this is not a form to email. Sit with them, work through it in
conversation, and take notes. Sections 3–6 deserve a dedicated session on their own.

⚠️ = **architecture-changing.** A wrong answer here means rework, not a tweak.

---

## Read this first: your stakeholder is the sales manager

He is your sponsor, a primary user, and — this is the trap — **not the person
whose daily work the system has to fit.**

Sales managers and sales reps want opposite things from a quoting tool:

| The manager wants | The reps want |
|---|---|
| Visibility into every deal | To not be watched |
| Consistent, controlled pricing | Freedom to close the deal in front of them |
| Data captured for reporting | Fewer fields to fill in |
| Approval gates on discounts | To not wait on anyone |

Both are legitimate. But a system built purely to the manager's brief becomes
surveillance with extra data entry, and reps route around it — they keep
quoting in Excel and paste the result in afterwards, or they don't use it at
all. That is the single most common way internal sales tools die, and it dies
quietly, six weeks after launch, when everyone is still saying it's going well.

**The countermeasure is simple: the system must make a rep's day faster on day
one.** Every piece of data the manager wants should fall out of work the rep
was already doing, not be added on top. If a field exists only for reporting,
it will be filled with garbage.

So, three things to insist on:

1. ⚠️ **Get an hour with two reps** — the strongest performer and the one most
   resistant to change. The second one tells you more.
2. ⚠️ **Watch a rep build a real quote** before you design anything. Time it.
   That number is your Phase 1 success metric.
3. Ask the manager directly: *"If the reps find this slower than Excel, what do
   we do?"* His answer tells you whether he understands the risk.

### Questions the manager cannot authoritatively answer

Don't accept his answer as final on these — get the right person:

| Topic | Ask instead |
|---|---|
| ERP/accounting API, hosting, security policy (Q98–105, Q112–117) | **IT / whoever owns the ERP** |
| Cost data accuracy, margin floors, tax treatment (Q49–50, Q95–97) | **Finance / accountant** |
| What *actually* slows a quote down (§3) | **The reps**, by observation |
| Product data, lead times, MOQ, what's really in stock (§4) | **Operations / production** |

If you can only add one person to the room, make it **whoever owns the ERP** —
Q98 has more power to blow up your estimate than any other question here.

### Manager-specific questions

Ask these of him directly; nobody else can answer them.

- ⚠️ You said "improve sales" — do you mean **more quotes out**, **faster
  turnaround**, **higher win rate**, or **better margin**? *(These pull in
  different directions. Rank them.)*
- ⚠️ You said "automation" — what specific task do you want to stop happening
  by hand? Name three.
- What number do you report upward today, and how long does producing it take you?
- What do you currently not know that you wish you did?
- How much of your own week goes into checking or fixing other people's quotes?
- Which of your reps is fastest at quoting, and what does he do differently?
- ⚠️ Are you willing to have discounts blocked by the system, or do you want a
  warning only? *(Hard gates change the approval architecture; warnings don't.)*
- ⚠️ Will using this be mandatory? Who enforces that, and starting when?

---

## 0. Before you ask anything: get artifacts

Do this first. The answers people *give* about their process and the process
they *actually run* are different documents.

- [ ] ⚠️ **Get 5–10 real quotes**, including the two most complicated ones they've
      sent in the last year and one that went badly wrong.
- [ ] Get the actual Excel files, with formulas intact — not exports.
- [ ] Get the product/price list in its current form.
- [ ] Get a blank copy of their terms & conditions.
- [ ] Get one example of every other document a deal produces (proforma invoice,
      order confirmation, packing list).
- [ ] **Watch someone build a real quote, start to finish, without helping.**
      This single hour will teach you more than the rest of this document.

---

## 1. Business context

1. What made you decide to fix this *now*? What changed?
2. What does the quoting process cost you today — in hours, in errors, in lost deals?
3. How many quotes go out per week? Per month? Is it seasonal?
4. What's the typical quote value? The range from smallest to largest?
5. What percentage of quotes convert? Do you know that number today?
6. ⚠️ **Six months after launch, how will you know this was worth building?**
   Get a concrete, measurable answer. "It's better" is not an answer.
7. Has anyone tried to fix this before? What happened?
8. Have you evaluated off-the-shelf tools? Which ones, and why did you rule them out?

## 2. The people

9. How many people will use this? How many create quotes vs. only view them?
10. What are the roles — reps, managers, finance, engineering, management?
11. ⚠️ What can each role see and do? Can a rep see another rep's quotes? Can they
    see cost and margin?
12. Where are they physically? One office, multiple, remote, travelling?
13. ⚠️ What languages do they work in? What languages do customers need documents in?
14. What devices? Desktop only, or do reps quote from the road?
15. How technical are they? What did the last software rollout here look like?
16. ⚠️ **Who is going to be annoyed by this system existing?** Someone always is.
    Usually whoever currently controls the spreadsheet.

## 3. The current process ⚠️

The most valuable section. Ask for stories, not descriptions.

17. Walk me through your last quote, from the customer's first email to the order.
18. Now walk me through the last one that was *difficult*. What made it difficult?
19. Where does a quote request come in — email, phone, WeChat, a web form, a portal?
20. Who touches a quote between request and send? In what order?
21. What has to be looked up or asked for before a quote can be finished?
22. What's the slowest part? Where does it sit waiting?
23. ⚠️ What gets checked before a quote goes out, and by whom?
24. How do you know what happened to a quote after you sent it? Who chases it?
25. What happens when a customer asks for a change? Do you edit it or start over?
26. How many rounds does a typical negotiation take?
27. What happens to a quote once it's accepted? Exactly what gets re-typed, and where?
28. Tell me about a quote that had a pricing error. What happened downstream?

## 4. Products & catalog

29. ⚠️ How many products? How many are actively quoted?
30. How is the catalog organized — categories, families, brands?
31. ⚠️ Do products have variants (size, color, material, voltage)? How many per product?
32. ⚠️ Units of measure: pieces, kg, meters, m², hours? Do you sell in one unit and
    price in another?
33. Do you sell kits, bundles, or assemblies made of other products?
34. ⚠️ **Are all products in the catalog, or do reps regularly add free-text lines
    for things that aren't?** What proportion?
35. How often does the catalog change? Who maintains it?
36. Do you quote products you don't stock or don't yet make?
37. Do you resell other manufacturers' products alongside your own?
38. What product data has to appear on the quote — specs, images, datasheets,
    certifications?
39. Do products have a lead time? A minimum order quantity? Do those vary by customer?

## 5. Pricing ⚠️⚠️

**The section that decides whether this project succeeds.** Budget a full session.
Whatever they tell you, assume there is one more rule they forgot to mention.

40. ⚠️ Where does the price of a line come from today? Trace one, concretely.
41. Is there a single list price per product, or several price lists?
42. ⚠️ Do different customers pay different prices for the same product? On what basis —
    contract, tier, region, volume, relationship?
43. ⚠️ Are there volume breaks? Are they per line, per product, per order, or per year?
44. Do you negotiate prices that then become standing for that customer? Where is
    that recorded today?
45. ⚠️ Is any price *calculated* rather than looked up? Show me the formula.
    (Ask this even if they said no in Q40 — formulas hide in spreadsheet columns.)
46. ⚠️ Who can discount, and up to what? What happens above that?
47. Is discount per line, per quote, or both? Percentage, fixed amount, or a
    target price they work backwards from?
48. Do you ever quote below cost deliberately? Under what circumstances?
49. ⚠️ Do you know your cost per product? Is it current? Who can see it?
50. What's the minimum acceptable margin? Is it enforced or advisory?
51. How do you price freight? Insurance? Packaging? Tooling or setup charges?
52. Are there surcharges — materials, fuel, small-order fees?
53. Do prices change during a quote's validity? What if the customer accepts a
    quote priced at a rate that has since changed?
54. How long is a quote valid? Is that negotiable per customer?
55. ⚠️ **Rounding: show me a quote where the line totals don't sum cleanly.**
    How do you round — per line or on the total? Up, down, or nearest?
56. ⚠️ Is there any pricing rule that is currently "in someone's head"?
    *(Ask this exact question, and wait through the silence.)*

## 6. Customers

57. How many customers? How many are active?
58. Do you segment them? By what — size, region, channel, industry?
59. ⚠️ Do you sell to distributors who resell? Do they get different pricing or
    different documents?
60. Do customers have multiple contacts, sites, or billing entities?
61. Do you quote to end users and their agents at the same time?
62. What customer data must appear on the quote?
63. Is there a customer credit check or approval step before quoting?
64. Where does customer data live today? Is it clean?

## 7. The quote document ⚠️

65. ⚠️ **What must appear on the quote for legal or contractual reasons?**
66. Can I see the current template? Is it fixed, or does it vary by customer or region?
67. Bilingual or single language? Which languages, and who translates?
68. ⚠️ Does it need a company chop/stamp? A signature? Whose?
69. Are terms & conditions attached, printed, or linked?
70. Do you show optional or alternative items? Do those affect the total?
71. Do you show unit prices, or only line and grand totals? Ever hide unit prices?
72. Do you group lines into sections? Show subtotals per section?
73. How is it delivered — PDF by email, printed, uploaded to a customer portal?
74. Does anything else get sent with it?

## 8. Approvals & workflow

75. ⚠️ Does any quote need approval before sending? What triggers it?
76. Who approves, and who covers for them when they're away?
77. How fast must approval happen? What's the cost of it being slow?
78. Can a quote be sent without approval in an emergency? Should the system allow that?
79. What happens if the approver rejects it?
80. ⚠️ Do you need a record of who approved what, and when? For audit, or for arguments?

## 9. International trade ⚠️

Skip only if they genuinely sell domestically.

81. ⚠️ Which countries do you sell to? Any you cannot sell to?
82. ⚠️ Which Incoterms do you use? Is it per customer, per deal, or standard?
83. Do you quote freight? Who calculates it, from what?
84. Do you need HS codes and country of origin on documents?
85. ⚠️ Do you produce a **proforma invoice**? Is that the document customers actually
    act on? Who produces it today?
86. What packing information do buyers ask for — weight, dimensions, cartons, CBM?
87. Port of loading and destination — quoted, or agreed later?
88. ⚠️ Payment terms: T/T deposit percentages, L/C, open account? Standard or negotiated?
89. Do you need export licences or certificates for anything you sell?
90. Do customers require documents in a specific format or through a specific portal?

## 10. Currency & tax ⚠️

91. ⚠️ Which currencies do you quote in? Which is your reporting currency?
92. ⚠️ Where does the exchange rate come from, and who decides it?
93. ⚠️ **If you quote in USD and the rate moves before acceptance, who absorbs it?**
    This is a business rule, not a technical one — get it decided in the room.
94. Do you add an FX buffer to quoted prices?
95. ⚠️ How is tax handled on export sales vs. domestic sales?
96. Does tax ever appear on the quote, or only at invoice?
97. *(Verify tax specifics with their accountant — do not design tax logic from
    a sales team's description of it.)*

## 11. Integrations

98. ⚠️ **What system does an accepted quote need to reach, and does it have an API?**
    Get the vendor, version, and whether it's cloud or on-premise.
99. Who owns that system? Will they cooperate, and on what timeline?
100. What exactly needs to transfer — the order, the customer, the products, all of it?
101. Does data need to come *back* — stock levels, costs, order status?
102. One-way or two-way? Real-time or batch?
103. What's the fallback if the integration is unavailable for a week?
104. Is there an existing CRM, email platform, or e-signature tool to connect to?
105. How does the team authenticate to other tools — WeCom, DingTalk, Microsoft,
     Google, or passwords?

## 12. Data migration

106. ⚠️ What has to come across, and what can be left behind?
107. How many products, customers, and historical quotes?
108. ⚠️ Who will clean the data? *(It is never as clean as they think, and this
     task always lands on someone who hasn't agreed to it yet.)*
109. Are there duplicate customer records? Inconsistent SKUs?
110. Do historical quotes need to be searchable, or is a PDF archive enough?
111. Who is the authority on which of two conflicting records is correct?

## 13. Operational reality

112. ⚠️ Where must this be hosted? Any policy on data leaving the country?
113. Who administers it after launch — users, permissions, catalog, templates?
114. What happens if it's down for an hour during business hours? For a day?
115. ⚠️ Who is responsible for backups, and who verifies a restore actually works?
116. Do you need an audit trail? Driven by policy, or by past disputes?
117. Any compliance requirement — ISO, customer audits, industry certification?
118. Who provides support to users when something breaks?

## 14. Scope & expectations

119. ⚠️ **If you could only have one thing from this system, what would it be?**
120. What's explicitly *not* in scope? Say it out loud now.
121. What would make you consider this a failure?
122. Is there a hard deadline, and what's driving it?
123. ⚠️ Who signs off on the finished product? Are they in this conversation?
124. Who decides when we disagree about a requirement?
125. Is there anyone whose approval we'll need who hasn't been mentioned yet?

## 15. Commercial — for you, not for them

126. ⚠️ Fixed price or time & materials? *(A CPQ system on fixed price with a
     vague pricing section is how contractors lose money.)*
127. Who owns the code and the IP?
128. Are you building once, or is this reusable for other clients?
129. ⚠️ Who maintains it in year two? Is that you, and is it paid?
130. What's the change-request process, and what does a change cost?
131. What are the payment milestones?
132. What happens to the system if the relationship ends?

---

## Red flags to listen for

Each of these predicts a specific, expensive failure:

| What you hear | What it means |
|---|---|
| "It's basically just Excel with a nicer interface." | They have not thought about pricing rules. Section 5 will take three sessions. |
| "Every quote is different." | There are rules; nobody has written them down. Budget for discovery you cannot yet scope. |
| "We'll figure out the pricing later." | Stop. Pricing *is* the system. Do not start without it. |
| "Just make it flexible." | Nobody has decided anything. Force decisions now or eat them later. |
| "Ask [person who isn't in the meeting]." | Your actual stakeholder is absent. Get them in the room. |
| "The data is pretty clean." | It is not. Ask to see it before you commit to a migration estimate. |
| "Can it also do invoicing / inventory / production?" | Scope creep toward a full ERP. Name the boundary in writing today. |
| "We need it before [trade show / fiscal year]." | Fixed deadline. Cut scope now, not in the last week. |

---

## The five questions that matter most

If you only get thirty minutes with the sales manager:

1. **Show me your five most complicated quotes.** (§0)
2. **Is there any pricing rule that's currently in someone's head?** (Q56)
3. **What system does an accepted quote need to reach, and does it have an API?** (Q98)
4. **"Improve sales" — more quotes, faster turnaround, higher win rate, or better
   margin? Rank them.** (manager section)
5. **Six months from now, how will you know this was worth building?** (Q6)

Then book the second meeting — with a rep, and with whoever owns the ERP.

*(§15 applies only if you're contracting externally. If you're an internal
developer and the sales manager is your internal client, skip it — but Q129,
"who maintains this in year two," still needs an answer from someone.)*
