# SYNTHETIC sample code for GigBid persona data_analyst. provenance: personas@228603469f77
from datetime import date

import pandas as pd
from google.cloud import bigquery


def run(day: date) -> int:
    rows = pd.DataFrame(crm_client.deals(updated_since=day))
    rows = rows.drop_duplicates("deal_id").assign(loaded_at=pd.Timestamp.utcnow())
    assert rows["amount"].ge(0).all(), "negative amounts"
    bigquery.Client().load_table_from_dataframe(rows, "raw.crm_deals").result()
    return len(rows)
