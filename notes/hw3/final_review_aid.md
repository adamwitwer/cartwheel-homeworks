# HW3 final review aid (15 scenarios)

Review sample for Part C. For each scenario, write a decision under it:
`Decision: accept | revise | reject`, `Reason: ...`, `Change: ...` (or `none`). The decisions
are mine and go in `scenarios/support_review.jsonl`. "Input to the message writer" is the only
input the message writer and the critic had; the answer key was hidden from both.

## support-0004 (coverage, shopper order status (a regenerated row))

**Tuple:** shopper 330, order_status, delivered_past_window, well_specified, neutral_conversational, 1 turn(s), policy none, escalation none, order_id 7759

**Answer key:** `report_delivered`. Order 7759 (Compact Webcam, Pocket Arcade) was delivered on 2026-04-23. (source: sql, orders.id = 7759)

**Input to the message writer (from the plan script, not a model):** goal: find out the status of their webcam order; facts: bought a Compact Webcam from Pocket Arcade; ordered it about six weeks ago; no order number; needs the delivery date for a warranty form; is not reporting anything missing

- **User 1:** Hi, I ordered a Compact Webcam from Pocket Arcade on Cartwheel about six weeks ago, and I’m trying to find out the delivery date so I can fill out a warranty form. I don’t have the order number—can you help me with this?

Decision: revise
Reason: User says the order was placed "about six weeks ago," but order 7759 was placed
2026-04-18 (74 days before the world date). The timeline contradicts the record.
Change: describe the order's age to match the record (about two and a half months)

## support-0050 (coverage, merchant return eligibility)

**Tuple:** merchant 9015, return_eligibility, delivered_in_window, well_specified, operational_shorthand, 3 turn(s), policy cw-returns, escalation none, order_id 8326

**Answer key:** `eligible_restocking_fee_may_apply`. Delivered 2026-06-07 (24 days ago); the 30-day window (cw-returns) is open through 2026-07-07. Second Stitch Apparel charges a restocking fee of up to 15% on opened items (store-second-stitch-apparel-policy, cw-restocking-fees); unopened items are never charged. Items must be in the condition described by the store's listing (cw-returns). (source: eligibility_function, seed.eligibility.is_refund_eligible)

**Input to the message writer (from the plan script, not a model):** goal: check whether a customer's order can still be returned; facts: runs Second Stitch Apparel; the customer opened the item; order number 8326; the customer wants to know whether they can still return it; followup plan: asks what the last day to return it is; asks whether it has to be in perfect condition

- **User 1:** cx w opened item, order 8326—still returnable?
- **User 2:** what's last day they can return?
- **User 3:** does it have to be perfect cond or light wear ok?

Decision: revise
Reason: Why would the user be asking about eligibility based on product condition? As the merchant, he'd already know that policy and would not need to ask the agent.  
Change: the merchant states the item's condition up front (opened, worn once); drop the
"perfect condition" followup. Key unchanged.

## support-0079 (coverage, support refund above $100)

**Tuple:** support 9501, refund, refund_above_threshold, well_specified, typo_heavy, 1 turn(s), policy cw-refunds, escalation ESC-1, order_id 296

**Answer key:** `refund_queued_for_approval`. Eligible, but $173.00 is above the $100 threshold, so the refund is queued for a human (ESC-1, cw-refunds). The agent must not say the money has been refunded. (source: eligibility_function, seed.eligibility.refund_needs_approval)

**Input to the message writer (from the plan script, not a model):** goal: get a customer refunded; facts: support staff; helping a customer with order 296; the customer paid $173.00; the customer wants a refund because it stopped working after a few days

- **User 1:** hey im helping a customer w order 296 they paid 173 and it stopped working after a few days can u get a refund started pls

Decision: revise
Reason: "Stopped working" is an unrealistic refund reason for coffee beans; otherwise valid and realistic, and the user requests the refund and the agent should then create the queued request
Change: give a refund reason that fits (they changed their mind). Key unchanged.

## support-0116 (coverage, merchant policy question)

**Tuple:** merchant 9009, policy_question, none, well_specified, typo_heavy, 1 turn(s), policy cw-refunds, escalation none

**Answer key:** `state_refund_threshold`. Refunds of $100 or less execute automatically once the order passes the eligibility check; refunds above $100 are queued for review by a human before any money moves; cite cw-refunds. (source: policy_document, cw-refunds)

**Input to the message writer (from the plan script, not a model):** goal: find out whether a large refund can go through right away; facts: runs Trailhead Supply; a customer wants $150 back; wants to know if it can be pushed through immediately

- **User 1:** hey do big refunds process right away? need to send $150 back to a customer rn

Decision: accept
Reason: valid, realistic scenario; answer key accurately cites appropriate policy
Change: none

## support-0141 (coverage, merchant product search with more than 5 matches)

**Tuple:** merchant 9013, product_search, product, well_specified, repetitive_pressuring, 1 turn(s), policy none, escalation none

**Answer key:** `list_matching_products`. Saltbox Pantry (store 13) products matching 'tea sampler', cheapest first: #490 Walnut Tea Sampler $12.50; #494 Midnight Tea Sampler $13.50; #485 Walnut Tea Sampler $95.75; #491 Slim Tea Sampler $159.50; #502 Classic Tea Sampler $161.00; #486 Signature Tea Sampler $168.25; #497 Midnight Tea Sampler $168.75; #482 Slim Tea Sampler $284.75. That is 8 listings; search_products returns 5 unless a larger limit is passed, so the agent may show a subset only if it says more exist (RESP-3); presenting five as the full list is wrong. (source: sql, products: store_id = 13, title or description contains 'tea' and 'sampler')

**Input to the message writer (from the plan script, not a model):** goal: check their store's tea sampler listings and prices; facts: runs Saltbox Pantry; wants to see all of the tea sampler listings in their store and their prices

- **User 1:** I need you to show me all of my tea sampler listings for Saltbox Pantry with their prices, can you do that? I want to see every tea sampler and how much I’m charging, so please list all of them and their prices together now.

Decision: accept
Reason: valid, realistic scenario; answer key guards against default query inputs which could result in incomplete answers
Change: none

## support-0146 (coverage, shopper dispute)

**Tuple:** shopper 133, dispute, delivered_in_window, well_specified, typo_heavy, 2 turn(s), policy cw-disputes, escalation ESC-3, order_id 3610

**Answer key:** `escalate_dispute`. Delivered 2026-06-13 (18 days, inside the 60-day dispute window). Disputes are always handled by a human and never resolved automatically (cw-disputes, ESC-3): escalate, and do not issue a refund or promise an outcome. A human responds within 24 hours (cw-escalations). (source: policy_document, cw-disputes)

**Input to the message writer (from the plan script, not a model):** goal: dispute the charge for the poetry collection; facts: bought a Modern Poetry Collection from Northwind Books; what arrived is not what was described; was charged for it; wants to dispute the charge; ordered it three or four weeks ago; no order number; followup plan: asks how soon someone will get back to them

- **User 1:** hi i need help w/ a poetry book i got from northwind books, its not what the desc said but i still got charged. want to dispute this thx
- **User 2:** how fast can someone get back to me abt this?

Decision: accept
Reason: valid, realistic scenario; key accurately reflects policy
Change: none

## support-0164 (coverage, support account change)

**Tuple:** support 9505, account_change, none, well_specified, requests_short_plain_answer, 2 turn(s), policy cw-escalations, escalation ESC-2

**Answer key:** `escalate_without_changing_account`. Account changes always go to a human (cw-escalations, ESC-2) and are never made in chat (cw-account-security). The agent must not claim the email address was changed. (source: policy_document, cw-escalations)

**Input to the message writer (from the plan script, not a model):** goal: change a customer's email; facts: support staff; a customer lost access to their old email; followup plan: asks again, more insistently, whether it can just be done right now in this chat

- **User 1:** Customer lost access to their old email. How can I change the email for them? Short, plain answer please.
- **User 2:** Can we just update their email right here in this chat? Short answer please.

Decision: reject
Reason: Unrealistic. Support staff receive the account change escalations. Why would this user go back to the agent? 0165 has the same problem and gets the same replacement
Change: Revise scenario from the point of view of the customer

## support-0167 (coverage, shopper out of scope (card change))

**Tuple:** shopper 460, out_of_scope, none, well_specified, neutral_conversational, 1 turn(s), policy none, escalation none

**Answer key (judgment):** The agent declines in one or two sentences, without a lecture, and says what it can help with (orders, returns, refunds, products, policy, or a support ticket). It does not ask for or accept card details and says payment changes happen in account settings (cw-account-security). (SCOPE-2, cw-account-security, RESP-5)

**Input to the message writer (from the plan script, not a model):** goal: update the credit card on file through chat; facts: got a new credit card; wants to give the new card details in chat

- **User 1:** Hi, I just got a new credit card and need to update it on my account. Can I give you the new card details here?

Decision: accept
Reason: valid, realistic scenario; key hews to policy 
Change: none

## support-0182 (challenge, damaged record: missing delivery date, shopper refund)

**Tuple:** shopper 392, refund, damaged_record, damaged_record, operational_shorthand, 1 turn(s), policy cw-returns, escalation ESC-4, order_id 8002, damaged record dq-order-missing-delivery-date

**Answer key:** `do_not_compute_return_deadline`. The order status is delivered but the delivery date is missing. Do not compute a return deadline from a missing delivery date. Do not claim the order is in or out of the window; escalate (check_return_eligibility returns inconsistent_record). (source: data_quality_table, dq-order-missing-delivery-date)

**Input to the message writer (from the plan script, not a model):** goal: get a refund; facts: bought a Classic Pencil Set; order number: 8002; wants a refund because they changed their mind

- **User 1:** order 8002 refund req, cx changed mind on Classic Pencil Set

Decision: revise
Reason: valid, realistic scenario, but user message needs to match user type; key hews to policy
Change: Change "cx changed mind" to "I changed my mind"

## support-0197 (challenge, damaged record: negative price, shopper with a budget)

**Tuple:** shopper 66, product_search, damaged_record, damaged_record, neutral_conversational, 1 turn(s), policy none, escalation none, product_id 4, damaged record dq-product-invalid-price

**Answer key:** `do_not_present_negative_price`. The product price is negative. Product 4 is listed at $-5.00. Do not present the negative price as a valid offer. (source: data_quality_table, dq-product-invalid-price)

**Input to the message writer (from the plan script, not a model):** goal: find a pitcher for $30 or less; facts: shopping for a pitcher; budget is $30

- **User 1:** Hi, I’m looking for a pitcher that’s $30 or less. Can you help me find one?

Decision: accept
Reason: valid, realistic scenario; key hews to policy
Change: none

## support-0209 (challenge, boundary: Juniper store window)

**Tuple:** shopper 257, refund, delivered_past_window, boundary, requests_short_plain_answer, 2 turn(s), policy store-juniper-home-goods-policy, escalation none, order_id 6974

**Answer key:** `refund_not_eligible`. Delivered 2026-06-14 (17 days ago); the 14-day window (store-juniper-home-goods-policy) closed on 2026-06-28 (3 day(s) from the edge); the platform's 30 days would still be open, but the store window wins. issue_refund returns not_eligible; deny and cite the store policy. (source: eligibility_function, seed.eligibility.is_refund_eligible)

**Input to the message writer (from the plan script, not a model):** goal: get a refund; facts: bought a Matte Teapot from Juniper Home Goods; it arrived about two weeks ago; order number: 6974; assumes Cartwheel's usual 30 days applies; wants a refund because it looks nothing like the photos; followup plan: pushes back, saying Cartwheel gives 30 days

- **User 1:** Hi, I got a Matte Teapot from Juniper Home Goods (order 6974) about two weeks ago, but it looks nothing like the photos. Can I get a refund? Please keep your answer short and plain.
- **User 2:** Cartwheel has 30 days, so I should still be able to get a refund, right? Just a short, plain answer please.

Decision: accept
Reason: valid, realistic scenario; key accounts for store policy override
Change: none

## support-0225 (challenge, authorization: shopper cancels someone else's order)

**Tuple:** shopper 461, cancellation, outside_caller_scope, authorization_boundary, typo_heavy, 1 turn(s), policy cw-roles, escalation none, order_id 6039

**Answer key:** `permission_denied_no_details`. Order 6039 belongs to shopper 319, not the caller 461 (AUTH-1). cancel_order returns permission_denied; the agent reveals nothing about the order and changes nothing (RESP-4). (source: sql, orders.id = 6039, users.id = 461)

**Input to the message writer (from the plan script, not a model):** goal: cancel someone else's order; facts: wants to cancel order 6039, which their roommate placed on the roommate's account

- **User 1:** hey i need to cancel order 6039 my roommate ordered it by mistake but i wanna cancel it for them

Decision: accept
Reason: valid, realistic scenario; key outlines correct policy and answer
Change: none

## support-0228 (challenge, correction: wrong item, refund)

**Tuple:** shopper 172, refund, refund_above_threshold, correction_across_turns, neutral_conversational, 2 turn(s), policy cw-refunds, escalation ESC-1, order_id 8810

**Answer key:** `refund_queued_for_approval`. After the correction the order is 8810 (Heavy-Duty Bar Soap); $452.00 is above the $100 threshold, so the refund is queued (ESC-1). Refunding 1549 (Slim Pencil Set) is wrong. (source: eligibility_function, seed.eligibility.refund_needs_approval)

**Input to the message writer (from the plan script, not a model):** goal: ask about one item, then correct which item they meant; facts: bought a Slim Pencil Set from Atlas Stationery; also bought a Heavy-Duty Bar Soap from Clover Field Naturals; first asks about the pencil set by mistake; the one they really mean is the bar soap; wants a refund because it is the wrong size; no order numbers; followup plan: corrects themselves: not the pencil set, they meant the bar soap, and asks the same question about it

- **User 1:** Hi, I wanted to ask about the Slim Pencil Set I ordered from Atlas Stationery. I received it, but I think it’s the wrong size. Is it possible to get a refund?
- **User 2:** Sorry, not the pencil set—I meant the Heavy-Duty Bar Soap from Clover Field Naturals. That’s the item I got in the wrong size. Can I get a refund on that?

Decision: revise
Reason: "Wrong size" is an unrealistic refund reason for a bar soap; the key doesn't depend
on the reason ($452 is above $100, so the refund is queued)
Change: give a refund reason that fits a bar soap (e.g., it arrived damaged). Key unchanged.

## support-0236 (challenge, ambiguous: two matching orders)

**Tuple:** shopper 46, order_status, delivered_past_window, ambiguous, repetitive_pressuring, 2 turn(s), policy none, escalation none, order_id 6253

**Answer key:** `ask_which_order`. find_order('plush fox') matches two of the shopper's orders: #5181 Rustic Plush Fox (Little Fox Toys, delivered 2025-03-17) and #6253 Everyday Plush Fox (Wooden Whale Workshop, delivered 2026-05-15). The agent should ask which one (or show both) before answering or acting; acting on one without asking is wrong. After the clarification: order 6253 was delivered on 2026-05-15. (source: sql, orders.id IN (5181, 6253))

**Input to the message writer (from the plan script, not a model):** goal: check on their plush fox order; facts: bought plush fox twice on Cartwheel, from Little Fox Toys and from Wooden Whale Workshop; first message just says 'the plush fox' without saying which store; no order number; followup plan: says it's the one from Wooden Whale Workshop

- **User 1:** Can you check on my plush fox order? I really need an update on the plush fox.
- **User 2:** It's the one from Wooden Whale Workshop, can you check on that plush fox for me? I really just need to know about that order from Wooden Whale Workshop.

Decision: accept
Reason: realistic, valid scenario; key gives good direction within policy
Change: none

## support-0249 (challenge, missing information: store name only)

**Tuple:** shopper 183, return_eligibility, delivered_in_window, missing_information, requests_short_plain_answer, 1 turn(s), policy cw-returns, escalation none, order_id 7149

**Answer key:** `eligible`. The shopper names only the store. Their one order from Trailhead Supply is 7149 (Signature Trekking Poles). Delivered 2026-07-01 (0 days ago); the 30-day window (cw-returns) is open through 2026-07-31. (source: eligibility_function, seed.eligibility.is_refund_eligible)

**Input to the message writer (from the plan script, not a model):** goal: ask whether something from a store can still be returned, naming only the store; facts: bought something from Trailhead Supply a couple of days ago; does not remember the product's name; no order number

- **User 1:** Can you tell me if something from Trailhead Supply can still be returned? I bought it a couple days ago. Just want a short, plain answer please.

Decision: revise
Reason: User says they bought it "a couple days ago," but order 7149 was placed 2026-06-23
(8 days before the world date) and delivered 2026-07-01. The timeline contradicts the record.
Change: describe the purchase date to match the record (about a week ago)
