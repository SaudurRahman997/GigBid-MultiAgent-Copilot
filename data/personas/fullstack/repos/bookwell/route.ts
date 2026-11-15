// SYNTHETIC sample code for GigBid persona fullstack. provenance: personas@1f579ad2e496
import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function POST(req: Request) {
  const { slotId, email } = await req.json();
  const booking = await db.$transaction(async (tx) => {
    const slot = await tx.slot.findUniqueOrThrow({ where: { id: slotId } });
    if (slot.bookedAt) throw new Error("Slot already taken");
    return tx.booking.create({ data: { slotId, email } });
  });
  return NextResponse.json(booking, { status: 201 });
}
