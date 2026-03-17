import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.drop)
        print("DnD registered!")

    def drop(self, event):
        print("Dropped:", event.data)

app = App()
app.after(500, app.destroy)
app.mainloop()
