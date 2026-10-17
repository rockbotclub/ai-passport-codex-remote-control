"""Read-only multi-chat overview; never changes the review/voice target."""
import hashlib
import struct

SUMMARY_SIZE = (104, 84)
LIST_SIZE = (216, 144)
FOOTER_SIZE = (216, 24)
HOME_PIXELS = sum(w * h // 8 for w, h in (SUMMARY_SIZE, LIST_SIZE, FOOTER_SIZE))
STATUS = {'offline': 0, 'idle': 1, 'working': 2, 'waiting': 3, 'done': 4, 'error': 5, 'syncing': 6}
EMPTY_LABELS = {
    'syncing': (('正在同步任务', '正在同步任务'), ('正在读取电脑任务状态', '正在读取电脑任务状态')),
    'idle': (('暂无任务', '暂无任务'), ('随时开始下一件事', '随时开始下一件事')),
    'done': (('本轮已结束', '本轮已结束'), ('随时开始下一件事', '随时开始下一件事')),
    'offline': (('电脑连接已断开', '电脑连接已断开'), ('请检查电脑端连接程序', '请检查电脑端连接程序')),
    'error': (('任务状态暂不确定', '任务状态暂不确定'), ('请在电脑上查看任务', '请在电脑上查看任务')),
}


def overview(activity, sessions, pending_threads=()):
    """Preserve lifecycle insertion order within each priority group."""
    states = {identity: value['status'] for identity, value in activity.items()}
    for thread in pending_threads:
        states[hashlib.sha256(thread.encode()).hexdigest()[:32]] = 'waiting'
    metadata = {hashlib.sha256(s['id'].encode()).hexdigest()[:32]: s for s in sessions}
    items = [(identity, status) for identity, status in states.items()
             if status in ('working', 'waiting') and
             (identity in metadata or activity.get(identity, {}).get('confirmed'))]
    visible = {identity for identity, _ in items}
    if any(status in ('working', 'waiting') and identity not in visible
           for identity, status in states.items()):
        states['@metadata'] = 'syncing'
    items.sort(key=lambda pair: pair[1] != 'waiting')
    waiting = sum(status == 'waiting' for _, status in items)
    status = ('waiting' if waiting else 'working' if items else
              'error' if 'error' in states.values() else
              'offline' if 'offline' in states.values() else
              'syncing' if 'syncing' in states.values() else
              'done' if 'done' in states.values() else 'idle')
    rows = []
    for identity, state in items[:3]:
        session = metadata.get(identity, {})
        rows.append({'project': session.get('project') or '无项目',
                     'title': session.get('title') or '未命名会话', 'status': state})
    return {'status': status, 'active': min(len(items), 999), 'waiting': min(waiting, 999),
            'rows': rows, 'remaining': max(0, len(items) - len(rows)),
            'syncing': 'syncing' in states.values() or any(identity not in metadata for identity, _ in items)}


class DashboardRenderer:
    def __init__(self, renderer):
        from PIL import ImageFont
        self.coverage = renderer.coverage
        self.fonts = {size: ImageFont.truetype(renderer.source, size) for size in (11, 12, 14, 15, 16)}
        self.cache = {}

    def supported(self, text, fallback):
        chosen = text if all(ord(c) in self.coverage for c in text if not c.isspace()) else fallback
        if any(ord(c) not in self.coverage for c in chosen if not c.isspace()):
            raise ValueError('字体缺少中文提示所需字符，请使用 --font 指定完整的中文字体。')
        return chosen

    def fit(self, text, size, width, lines=1):
        text = self.supported(' '.join(text.split()), '请在电脑上查看文字')
        font = self.fonts[size]
        result, line = [], ''
        for char in text:
            if font.getlength(line + char) > width and line:
                result.append(line)
                line = ''
            line += char
        result.append(line)
        if len(result) > lines:
            result = result[:lines]
            tail = result[-1]
            suffix = self.supported('…', '...')
            while tail and font.getlength(tail + suffix) > width:
                tail = tail[:-1]
            result[-1] = tail + suffix
        return result

    def text(self, draw, xy, text, size, *, width=None, lines=1, centered=False):
        font = self.fonts[size]
        fitted = self.fit(text, size, width if width is not None else 216, lines)
        for i, line in enumerate(fitted):
            x, y = xy
            if centered:
                x -= font.getlength(line) / 2
            draw.text((x, y + i * (size + 7)), line, font=font, anchor='lt', fill=1)

    def frame(self, model):
        from PIL import Image, ImageDraw
        key = (model['status'], model['active'], model['waiting'], model['remaining'], model.get('syncing', False),
               tuple((r['project'], r['title'], r['status']) for r in model['rows']))
        if key in self.cache:
            return self.cache[key]
        summary = Image.new('1', SUMMARY_SIZE)
        rows = Image.new('1', LIST_SIZE)
        footer = Image.new('1', FOOTER_SIZE)
        sd, rd, fd = (ImageDraw.Draw(image) for image in (summary, rows, footer))
        title = {'waiting': ('需要你处理', '需要你处理'), 'working': ('正在工作', '正在工作'),
                 'idle': EMPTY_LABELS['idle'][0], 'offline': EMPTY_LABELS['offline'][0],
                 'done': EMPTY_LABELS['done'][0], 'error': EMPTY_LABELS['error'][0],
                 'syncing': EMPTY_LABELS['syncing'][0]}[model['status']]
        self.text(sd, (0, 2), self.supported(*title), 15, width=104)
        for y, text, fallback, value in ((34, '运行中', '运行中', model['active'] - model['waiting']),
                                       (57, '待处理', '待处理', model['waiting'])):
            self.text(sd, (0, y), self.supported(text, fallback), 12, width=74)
            number = str(value)
            self.text(sd, (104 - self.fonts[16].getlength(number), y - 2), number, 16, width=104)
        count = len(model['rows'])
        for i, row in enumerate(model['rows']):
            y = i * 45 + (12 if count == 1 else 3)
            state = self.supported('待处理' if row['status'] == 'waiting' else '运行中',
                                   '待处理' if row['status'] == 'waiting' else '运行中')
            state_width = self.fonts[11].getlength(state)
            self.text(rd, (8, y), row['project'], 11, width=int(196 - state_width - 8))
            self.text(rd, (208 - state_width, y), state, 11, width=int(state_width + 1))
            title = row['title']
            self.text(rd, (8, y + 19), title, 16 if count == 1 else 14,
                      width=200, lines=3 if count == 1 else 1)
        if not count:
            empty, sub = EMPTY_LABELS[model['status']]
            self.text(rd, (108, 84), self.supported(*empty), 16, width=216, centered=True)
            self.text(rd, (108, 113), self.supported(*sub), 12, width=216, centered=True)
        remaining = model['remaining']
        caption = (self.supported('正在同步任务', '正在同步任务') if model.get('syncing') else
                   self.supported(f'还有 {remaining} 个会话', f'还有 {remaining} 个会话') if remaining else
                   self.supported('暂无活跃会话', '暂无活跃会话') if model['status'] in ('idle', 'done') else
                   self.supported(f'{model["active"]} 个活跃会话', f'{model["active"]} 个活跃会话') if count else '')
        self.text(fd, (0, 7), caption, 11, width=106)
        action = self.supported('按键查看全部', '按键查看全部')
        self.text(fd, (216 - self.fonts[11].getlength(action), 7), action, 11, width=106)
        mask = sum(1 << i for i, row in enumerate(model['rows']) if row['status'] == 'waiting')
        result = struct.pack('!BBHHBB', 9, STATUS[model['status']], model['active'], model['waiting'], count, mask)
        result += summary.tobytes() + rows.tobytes() + footer.tobytes()
        if len(result) != 8 + HOME_PIXELS:
            raise ValueError('任务总览位图大小无效')
        if len(self.cache) > 24:
            self.cache.clear()
        self.cache[key] = result
        return result
