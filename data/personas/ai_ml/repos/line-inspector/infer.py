# SYNTHETIC sample code for GigBid persona ai_ml. provenance: personas@1f579ad2e496
import cv2
import torch

model = torch.jit.load("defects.pt").eval()


def inspect(path: str) -> dict:
    img = cv2.imread(path)
    img = cv2.createCLAHE(clipLimit=2.0).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    with torch.no_grad():
        score = model(torch.from_numpy(img).float()[None, None] / 255).sigmoid().item()
    return {"defect": score > 0.5, "score": round(score, 3)}
