from dataclasses import dataclass
from typing import Any


@dataclass(eq=False)
class Node:
    data: Any
    prev: 'Node | None' = None
    next: 'Node | None' = None


class LinkedBook:
    """
    双向链表实现的好友列表, 同时引入哈希表实现O(1)查找
    """
    def __init__(self):
        self.head = self.tail = None
        self.index = {}

    def __len__(self):
        return len(self.index)

    def __iter__(self):
        node = self.head
        while node:
            yield node.data
            node = node.next

    def get(self, uid):
        return self.index[uid].data

    def insert(self, data, anchor=None, before=False):
        if data['id'] in self.index:
            raise ValueError('内部 ID 已存在，未覆盖原资料')
        target = self.index[anchor] if anchor else None
        node = Node(data)
        if target:
            left, right = (target.prev, target) if before else (target, target.next)
        else:
            left, right = self.tail, None
        node.prev, node.next = left, right
        if left:
            left.next = node
        else:
            self.head = node
        if right:
            right.prev = node
        else:
            self.tail = node
        self.index[data['id']] = node

    def remove(self, uid):
        node = self.index.pop(uid)
        if node.prev:
            node.prev.next = node.next
        else:
            self.head = node.next
        if node.next:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
        node.prev = node.next = None
        return node.data

    def update(self, uid, data):
        if data['id'] != uid:
            raise ValueError('不能修改内部 ID')
        self.index[uid].data = data

    def move(self, uid, anchor=None, before=False):
        if anchor == uid:
            return
        if anchor is not None and anchor not in self.index:
            raise KeyError(anchor)
        self.insert(self.remove(uid), anchor, before)

    def validate(self):
        seen = set()
        last = None
        node = self.head
        while node:
            assert node.prev is last
            assert node.data['id'] not in seen
            assert self.index[node.data['id']] is node
            seen.add(node.data['id'])
            last, node = node, node.next
        assert last is self.tail and seen == set(self.index)
        return True
