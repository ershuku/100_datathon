# Cashier Video Checker — Rules for Aibar

Source: the organisers' training clips and the team's per-clip notes (not included here).

## Objective

Minimize false positives while treating missed violations as unacceptable. Never automatically classify an unresolved case as compliant. Video alone cannot guarantee zero false negatives: missing footage, occlusion, ambiguous actions, and inconsistent labels require review.

These are rules inferred from the supplied annotations, not a verified operating procedure. Resolve the conflicts below before treating the rules as final training labels.

## Decision outcomes

| Outcome | Use when | Action |
| --- | --- | --- |
| Confirmed violation | A prohibited action is observed, or an applicable deadline passes with an obligation demonstrably unmet. | Report every supported violation with evidence and timestamp. |
| Confirmed compliant | All applicable obligations in the completed observed scenario are supported by evidence. | Clear the evaluated scenario and state its scope. |
| In progress | An obligation is pending and its deadline has not passed. | Continue monitoring; do not mark the transaction complete. |
| Review required | Evidence is incomplete, uncertain, or contradictory. | Keep unresolved and escalate; never silently clear. |

A clip ending during processing is not proof of a violation or completed compliance. If later footage is unavailable and the final outcome must be decided, send the unresolved obligation for review. A violation already observed remains a violation even if the clip later ends or the cashier subsequently corrects it.

## Scenario classifications

Classifications overlap. Apply every relevant rule to each video. Arrows indicate required dependencies; independent preparation steps may be reordered. Optional actions must not break another rule.

### 1. Customer identification and intake

- **Mandatory:** customer presents ID → cashier verifies it against that customer → accept that customer's cash or cash bag → retain the identity-to-transaction association.
- **Optional:** sitting, conversation, returning ID after verification. Checking both sides of the ID is not consistently required.
- **Unacceptable:** accepting cash/bag without identification when the complete intake is visible; using customer B's ID for customer A's cash.

### 2. Customer cash counting and deposit

- **Mandatory:** identified intake → prepare banknotes if needed → machine-count → collect counted cash → put the full deposit in the safe before the customer leaves → apply safe-security rules.
- **Optional:** removing/replacing bands or envelopes, temporary desk placement during processing, laptop entry.
- **Unacceptable:** customer departure before counting and storage finish; deposit cash remaining unsecured after departure. Returning part of the counted deposit to the customer is also labelled as a violation; do not generalize this to authorized withdrawals or change-giving without further rules.

### 3. Transition between customers

- **Mandatory:** count and secure customer A's cash → A leaves → begin customer B's separate transaction. These examples require A's cash secured before B enters.
- **Optional:** transaction recording, returning ID, bundling before storage.
- **Unacceptable:** A's cash remaining on the desk after A leaves or when B enters; mixing customers' cash; placing B's uncounted cash onto A's counted cash.

### 4. Cash bag and multiple-bundle processing

- **Mandatory:** open bag → extract bundles → prepare and machine-count every bundle → collect counted cash → store in safe → close safe; apply locking and exit rules when relevant.
- **Optional:** scissors, bundle order, rewrapping, combining fully counted bundles from the same batch, laptop entry.
- **Unacceptable:** storing uncounted cash; treating a partially counted batch as fully counted; leaving without meeting applicable exit obligations.

### 5. Internal cash counting without a customer

- **Mandatory:** identify working batch → prepare if needed → machine-count → collect counted cash. Secure it when a relevant deadline occurs, such as cashier departure.
- **Optional:** temporary desk placement, bundling, journal entry, immediate storage, putting a phone away.
- **Unacceptable:** leaving cash unsecured when exiting; treating uncounted cash as counted; mixing unchecked rejected notes with accepted notes.
- **Important:** cash on the desk during ongoing attended work is not automatically a violation.

### 6. Safe access and withdrawal

- **Mandatory:** open safe → retrieve/deposit cash → close and lock after access ends → resume other work. Locking is required before sitting down to count withdrawn cash.
- **Optional:** taking keys immediately while staying in the room. Keys may stay in the lock while the cashier is present.
- **Unacceptable:** continuing unrelated work with the safe open/unlocked; leaving it unsecured. A closed door does not itself prove locking.

### 7. Rejected-banknote handling

- **Mandatory:** retrieve rejected notes → keep separate from accepted notes → inspect under the detector → merge only after clearance.
- **Optional:** individual inspection; grouped inspection; temporary placement of checked notes on the desk.
- **Unacceptable:** merging rejected and accepted notes before checking. Rejection alone does not prove counterfeiting; detector use alone does not establish an authentic result if that result is not observable.

### 8. Securing materials before departure

- **Mandatory:** identify cash, journal, and designated protected items → collect → put in safe → lock → leave.
- **Optional:** bundling cash, arranging items, standing before collection.
- **Unacceptable:** leaving protected materials on the desk when exiting. A bag left behind is also flagged; clarify its type before applying a universal bag-storage rule.

### 9. Equipment shutdown and exit security

- **Mandatory:** finish work → secure protected materials → put laptop in the approved secure state → shut down applicable equipment → lock safe → take keys → switch off lights → exit → close door. Independent pre-exit steps may be reordered.
- **Optional:** standing at different points; taking keys earlier; reordering equipment shutdown and desk clearing.
- **Unacceptable:** leaving keys behind, leaving the laptop active, or leaving the safe unsecured. Counter-machine shutdown and lights-off appear in the full exit sequence, but omission from a shortened description is not evidence they were skipped.

### 10. Room entry and door control

- **Mandatory:** enter → close entrance door → start work.
- **Optional:** arranging belongings and preparing equipment after closing the door.
- **Unacceptable:** starting work with the entrance door left open. An intruder or observer is not required for the violation.

### 11. Personal belongings at the workstation

- **Mandatory:** put personal belongings away from the cash-working surface → begin work → keep the surface free of personal belongings during cash handling.
- **Optional:** briefly setting belongings down on arrival if removed before work; putting a phone in a pocket.
- **Unacceptable:** starting work with a bag/jacket on the desk; placing coffee, gum, or other personal belongings alongside cash.

## Deadlines and detection principles

| Obligation | Deadline |
| --- | --- |
| Verify customer identity | Before accepting their cash/bag |
| Count received cash | Before storing it as a completed deposit |
| Secure customer cash | Before that customer leaves and before the next enters |
| Close and lock safe after withdrawal | Before resuming counting or unrelated work |
| Inspect rejected notes | Before merging with accepted notes |
| Secure materials, equipment, safe, and keys | Before cashier departure |
| Close entrance door | Before starting work |
| Remove personal belongings | Before work and throughout cash handling |

1. **Track state and ownership:** customer/transaction, cash batch, counted/uncounted/rejected/checked/stored status, safe open/closed/locked/unknown, key location, desk contents, equipment, door, and cashier presence.
2. **Require evidence:** missing action text is not proof of a missed action. A hand near the safe does not prove deposit or locking. Unknown initial states remain unknown.
3. **Use event deadlines:** the data does not establish valid fixed time limits. Do not invent a rule such as “cash on desk for 10 seconds.”
4. **Allow harmless variation:** posture, bands, envelopes, and independent preparation steps need not exactly match a reference pipeline.
5. **Report multiple violations:** one detected issue must not suppress other applicable checks.
6. **Keep uncertainty visible:** uncertain observations enter review, not the compliant class. Review referrals are not confirmed violations or resolved detections.
7. **Evaluate across viewpoints:** front/behind views can hide ID, keys, or safe actions. Use available evidence rather than assuming an unobserved action did not happen.

## Validation target

Use independently reviewed test videos and measure results per rule, not only per video. Target zero missed violations on that test set, report false-positive alerts and review volume separately, and track whether every review case is resolved. Test truncated clips, occlusions, customer transitions, cash ownership, safe state, keys, rejected notes, and differing viewpoints.

The clip descriptions support initial rule design; they do not demonstrate a zero-false-negative guarantee on future footage.
