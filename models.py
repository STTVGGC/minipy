from tortoise import fields
from tortoise.models import Model


class Message(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50)
    content = fields.TextField()
    likes = fields.IntField(default=0)  # 添加点赞字段，默认值为0
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"

    def __str__(self):
        return f"{self.name}: {self.content[:20]}"


class Comment(Model):
    id = fields.IntField(pk=True)
    message = fields.ForeignKeyField('models.Message', related_name='comments', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=50)
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "comments"

    def __str__(self):
        return f"Comment by {self.name} on message {self.message_id}: {self.content[:20]}"
