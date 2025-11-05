from tortoise import fields
from tortoise.models import Model
from datetime import datetime


class Message(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50)  # 保留原字段以便兼容
    user = fields.ForeignKeyField('models.User', related_name='messages', null=True, on_delete=fields.SET_NULL)
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
    name = fields.CharField(max_length=50)  # 保留原字段以便兼容
    user = fields.ForeignKeyField('models.User', related_name='comments', null=True, on_delete=fields.SET_NULL)
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "comments"

    def __str__(self):
        return f"Comment by {self.name} on message {self.message_id}: {self.content[:20]}"


class User(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True, index=True)
    password_hash = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"

    def __str__(self):
        return self.username
