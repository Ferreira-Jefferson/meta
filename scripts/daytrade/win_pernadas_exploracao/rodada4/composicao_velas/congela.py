import pandas as pd, numpy as np
df = pd.read_csv("descoberta.csv")
f = df[df.z.abs() > 3].copy()
f.to_csv("regras_congeladas.csv", index=False)
print(len(f)); print(f.round(3).to_string())
