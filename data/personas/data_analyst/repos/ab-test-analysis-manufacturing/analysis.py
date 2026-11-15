# SYNTHETIC sample code for GigBid persona data_analyst. provenance: personas@1f579ad2e496
import pandas as pd
from scipy import stats

df = pd.read_csv("responses.csv")
a, b = df[df.group == "A"].score, df[df.group == "B"].score
t, p = stats.ttest_ind(a, b, equal_var=False)
print(f"diff={b.mean() - a.mean():.2f}  p={p:.3f}  n={len(df)}")
print(df.groupby("segment").score.agg(["mean", "count"]).round(2))
