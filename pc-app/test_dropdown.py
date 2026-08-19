import tkinter as tk
from tksheet import Sheet

root = tk.Tk()
sheet = Sheet(root, data=[["1", "2", "3", "RestA", "5", "6", "high", "8"]])
sheet.pack(fill="both", expand=True)

sheet.create_dropdown(r=0, c=3, values=["RestA", "RestB"], set_value="")

# Check value
print("Value in cell 0,3:", sheet.get_cell_data(0, 3))
