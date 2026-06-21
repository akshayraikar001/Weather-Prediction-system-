import pandas as pd

df = pd.read_excel("../archive/weather_data.xlsx")

print(df["last_updated_epoch"].min())
print(df["last_updated_epoch"].max())
print(df.shape)
