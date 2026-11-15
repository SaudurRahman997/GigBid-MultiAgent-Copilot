# SYNTHETIC sample code for GigBid persona ai_ml. provenance: personas@1f579ad2e496
TOOLS = [calendar.free_slots, calendar.hold_slot, crm.lookup_contact]


def run(request: str, approve) -> str:
    """Plan with tool calls; anything that leaves the system needs human approval."""
    plan = llm.plan(request, tools=TOOLS)
    for call in plan.calls:
        if call.sends_external and not approve(call):
            return "Waiting for approval"
        audit.log(call.name, call.args, call.run())
    return plan.summary
