from tortoise import fields
from tortoise.models import Model


class Message(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50)
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"

    def __str__(self):
        return f"{self.name}: {self.content[:20]}"
