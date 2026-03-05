import pandas as pd

class Upload():
    def open(self, path):
        self.path = path
        return self

    def transform(self):
        df = pd.read_excel(self.path, sheet_name='Свод', header=1)
        self.df = df
        return df








# Create your models here.
#
# class Debitor(models.Model):
#     title = models.CharField(max_length=100)
#     content = models.TextField()
#     def __str__(self):
#         return self.title