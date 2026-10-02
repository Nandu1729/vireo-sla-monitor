# To: Neha Kulkarni, Support Operations Manager

**Subject: The Morning team is inheriting an overnight coverage problem**

The current first-response breach rate is **25.2%**: 563 of 2,230 tickets created in April-June 2026 missed the channel target. Completed tickets generated **₹186,900 in SLA credits** in that quarter.

The report does show most breaches against Morning agents, but that is not the same as showing that Morning agents caused them. The export records the agent who resolved each ticket, not the person who gave the first response. Under Vireo's reporting convention, an agent can inherit a late ticket and still carry the breach.

The stronger finding is the time at which demand entered the queue. Tickets created during the Night shift breached at **80.4%** (405 of 504), versus 9.4% in Morning and 9.0% in Day. Of the 482 breaches recorded against Morning resolvers, **394 (81.7%) were created overnight**.

There is a clear change point. The roster shows two Indore Night assignments through 29 June 2025 and no Night assignment after that date, despite the policy saying Indore provides overnight coverage. Before the change, the overall breach rate was 9.2%. In the following six months it was 24.8%. Monthly SLA credits rose from ₹10,500 in June 2025 to ₹36,400 in July, then settled around ₹60,000-₹70,000 as volume grew. This reconciles Arjun's longer-term observation with Priya's view that recent months look flat.

**Recommendation:** run a two-week, cost-neutral pilot that restores two existing Indore assignments to Night coverage. Review results weekly by the shift in which tickets were created. Keep the recorded-agent table for workload follow-up, but do not use it for disciplinary conversations until the export includes the first-response agent ID.

Set a 90-day goal to reduce breaches from **25.2% to 15.0% without adding headcount**. At 650 tickets a week and ₹350 per breach, that improvement is worth approximately **₹303,000 per quarter** in avoided credits:

`(25.25% - 15.0%) × 650 × 13 × ₹350`.

The attached tool applies the policy targets, converts UTC to IST, removes 616 migration duplicates, joins the dated roster, and produces weekly agent and shift files. Its 120-ticket stratified arithmetic check found no SLA classification errors. The main limitation remains attribution: the pack can show where and when the queue failed, but not which human sent the first reply.
