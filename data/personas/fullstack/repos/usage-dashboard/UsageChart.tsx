// SYNTHETIC sample code for GigBid persona fullstack. provenance: personas@1f579ad2e496
import { useMemo, useState } from "react";

type Point = { day: string; events: number; account: string };

export function UsageChart({ data }: { data: Point[] }) {
  const [account, setAccount] = useState<string>("all");
  const rows = useMemo(
    () => data.filter((d) => account === "all" || d.account === account),
    [data, account],
  );
  return (
    <section aria-label="Usage">
      <select value={account} onChange={(e) => setAccount(e.target.value)}>
        <option value="all">All accounts</option>
      </select>
      <Bars rows={rows} />
    </section>
  );
}
