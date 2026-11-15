# SYNTHETIC sample code for GigBid persona ai_ml. provenance: personas@228603469f77
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

features = pd.read_parquet("features.parquet")
X, y = features.drop(columns=["churned_30d"]), features["churned_30d"]
model = CalibratedClassifierCV(HistGradientBoostingClassifier(max_depth=6), cv=3)
print("AUC", cross_val_score(model, X, y, cv=TimeSeriesSplit(5), scoring="roc_auc").mean())
model.fit(X, y)
