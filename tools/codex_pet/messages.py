"""Chinese diagnostics; machine-readable reason codes remain stable."""
import argparse
import errno
import re


REASONS = {
    'accessibility-denied': '未获得辅助功能权限，请为连接程序开启权限',
    'app-unavailable': 'Codex 未运行或无法确定目标应用',
    'windows-unavailable': 'Codex 窗口不可用',
    'chat-not-found': '未找到所选会话，请在电脑上打开该会话',
    'multiple-chat-views': '发现多个所选会话视图',
    'writable-editor-not-found': '未找到可输入的编辑框',
    'multiple-writable-editors': '发现多个可输入的编辑框',
    'press-unsupported': '目标按钮不支持按下操作',
    'press-not-acknowledged': '尚未确认按钮操作结果，请在电脑上检查',
    'accessibility-tree-limit': '无法完整读取辅助功能界面',
    'invalid-composer-request': '输入框操作请求无效',
    'composer-button-unavailable': '输入框操作按钮不可用',
    'multiple-composer-buttons': '发现多个输入框操作按钮',
    'chat-changed': '所选会话已变化',
    'dictation-already-active': '语音输入已在进行，请先在电脑上结束',
    'dictation-start-not-ready': '语音输入尚未就绪，请检查电脑端麦克风权限',
    'accessibility-view-unavailable': '无法读取 Codex 界面，请检查辅助功能权限',
    'send-disabled': '发送按钮不可用，请检查输入内容和附件',
    'send-input-required': '暂无可发送内容，请先输入文字',
    'composer-focus-failed': '输入框未获得焦点',
    'doubao-unavailable': '豆包输入法未运行',
    'doubao-input-required': '请切换至豆包输入法，并将长按语音快捷键设为左 Control 键',
    'modifier-held': '请先松开电脑键盘上的修饰键',
    'codex-focus-required': '请将 Codex 切换到前台',
    'key-dispatch-failed': '无法发送或释放语音快捷键',
    'dictation-interrupted': '语音输入已中断',
    'dictation-timeout': '语音输入超时',
    'dictation-target-changed': '语音输入的目标或焦点已变化',
    'doubao-state-unavailable': '无法读取豆包输入法状态',
    'doubao-start-unconfirmed': '尚未确认豆包语音启动，请检查左 Control 键快捷设置',
    'doubao-insert-pending': '豆包语音文字仍在插入，请在电脑上检查',
    'key-release-unconfirmed': '尚未确认语音快捷键已释放，请在电脑上检查',
    'helper-failed': '电脑端控制程序执行失败，请检查应用和权限',
}


def reason_text(reason):
    return REASONS.get(reason, REASONS['helper-failed'])


def system_error(error):
    """Do not forward untranslated OS text, filenames or arbitrary server errors."""
    if hasattr(error, 'reason'):
        return reason_text(error.reason)
    if isinstance(error, ImportError):
        return '缺少依赖，请在虚拟环境中安装 requirements.txt 中的依赖'
    if isinstance(error, (ValueError, RuntimeError)) and re.search(r'[\u4e00-\u9fff]', str(error)):
        return str(error)
    if isinstance(error, TimeoutError):
        return '等待响应超时'
    return {
        errno.EACCES: '权限不足', errno.EPERM: '操作未获授权',
        errno.ENOENT: '找不到所需文件或设备', errno.EADDRINUSE: '监听端口已被占用',
        errno.ECONNREFUSED: '连接被拒绝', errno.ECONNRESET: '连接已重置',
        errno.ETIMEDOUT: '连接超时', errno.ENETUNREACH: '网络不可达',
        errno.EHOSTUNREACH: '无法连接目标设备', errno.ENODEV: '设备不可用',
        errno.EIO: '设备读写失败',
    }.get(getattr(error, 'errno', None), '操作失败，请检查配置、依赖和连接')


class ChineseHelpFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups, '用法：' if prefix is None else prefix)


class ChineseArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('formatter_class', ChineseHelpFormatter)
        kwargs.setdefault('add_help', False)
        super().__init__(*args, **kwargs)
        self._positionals.title = '位置参数'
        self._optionals.title = '可选参数'
        self.add_argument('-h', '--help', action='help', help='显示帮助信息并退出')

    def error(self, message):
        replacements = {
            'the following arguments are required:': '缺少必需参数：',
            'unrecognized arguments:': '无法识别的参数：',
            'invalid choice:': '无效选项：', 'choose from': '可选值为',
            'expected one argument': '需要一个参数值',
            'expected at least one argument': '至少需要一个参数值',
            'not allowed with argument': '不能同时使用参数',
            'one of the arguments': '以下参数中', 'is required': '必须指定一个',
            'ambiguous option:': '参数不明确：', 'could match': '可能匹配',
            'ignored explicit argument': '此参数不接受值',
        }
        for source, target in replacements.items():
            message = message.replace(source, target)
        message = re.sub(r'\bargument\b', '参数', message)
        self.print_usage(__import__('sys').stderr)
        self.exit(2, f'{self.prog}：错误：{message}\n')
