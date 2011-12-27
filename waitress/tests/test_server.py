import errno
import socket
import unittest

class TestWSGIServer(unittest.TestCase):
    def _makeOne(self, application, host='127.0.0.1', port=62122,
                 _dispatcher=None, adj=None, map=None, _start=True, 
                 _sock=None):
        from waitress.server import WSGIServer
        class TestServer(WSGIServer):
            def bind(self, v):
                pass
        return TestServer(
            application,
            host=host,
            port=port,
            map=map,
            _dispatcher=_dispatcher,
            _start=_start,
            _sock=_sock)
    
    def _makeOneWithMap(self, adj=None, _start=True, host='127.0.0.1',
                        port=62122, app=None):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        return self._makeOne(
            app,
            host=host,
            port=port,
            map=map,
            _sock=sock,
            _dispatcher=task_dispatcher,
            _start=_start,
            )

    def test_ctor_start_true(self):
        inst = self._makeOneWithMap(_start=True)
        self.assertEqual(inst.accepting, True)
        self.assertEqual(inst.socket.listened, 1024)

    def test_ctor_start_false(self):
        inst = self._makeOneWithMap(_start=False)
        self.assertEqual(inst.accepting, False)

    def test_get_server_name_empty(self):
        inst = self._makeOneWithMap(_start=False)
        result = inst.get_server_name('')
        self.assertTrue(result)

    def test_get_server_name_with_ip(self):
        inst = self._makeOneWithMap(_start=False)
        result = inst.get_server_name('127.0.0.1')
        self.assertTrue(result)

    def test_get_server_name_with_hostname(self):
        inst = self._makeOneWithMap(_start=False)
        result = inst.get_server_name('fred.flintstone.com')
        self.assertEqual(result, 'fred.flintstone.com')

    def test_add_task(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.add_task(task)
        self.assertEqual(inst.task_dispatcher.tasks, [task])
        self.assertFalse(task.serviced)

    def test_readable_not_accepting(self):
        inst = self._makeOneWithMap()
        inst.accepting = False
        self.assertFalse(inst.readable())
        
    def test_readable_maplen_gt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {'a':1, 'b':2}
        self.assertFalse(inst.readable())

    def test_readable_maplen_lt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {}
        self.assertTrue(inst.readable())

    def test_readable_maintenance_false(self):
        import sys
        inst = self._makeOneWithMap()
        inst.next_channel_cleanup = sys.maxint
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertEqual(L, [])
        self.assertEqual(inst.next_channel_cleanup, sys.maxint)

    def test_readable_maintenance_true(self):
        inst = self._makeOneWithMap()
        inst.next_channel_cleanup = 0
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertEqual(len(L), 1)
        self.assertNotEqual(inst.next_channel_cleanup, 0)

    def test_writable(self):
        inst = self._makeOneWithMap()
        self.assertFalse(inst.writable())
        
    def test_handle_read(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_read(), None)

    def test_handle_connect(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_connect(), None)

    def test_handle_accept_wouldblock_socket_error(self):
        inst = self._makeOneWithMap()
        ewouldblock = socket.error(errno.EWOULDBLOCK)
        inst.socket = DummySock(toraise=ewouldblock)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)

    def test_handle_accept_other_socket_error(self):
        import socket
        inst = self._makeOneWithMap()
        eaborted = socket.error(errno.ECONNABORTED)
        inst.socket = DummySock(toraise=eaborted)
        inst.adj = DummyAdj
        def foo(): raise socket.error
        inst.accept = foo
        L = []
        def log_info(msg, type):
            L.append(msg)
        inst.log_info = log_info
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)
        self.assertEqual(len(L), 1)

    def test_handle_accept_noerror(self):
        inst = self._makeOneWithMap()
        innersock = DummySock()
        inst.socket = DummySock(acceptresult=(innersock, None))
        inst.adj = DummyAdj
        L = []
        inst.channel_class = lambda *arg, **kw: L.append(arg)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, True)
        self.assertEqual(innersock.opts, [('level', 'optname', 'value')])
        self.assertEqual(L, [(inst, innersock, None, inst.adj)])

    def test_maintenance(self):
        inst = self._makeOneWithMap()
        class DummyChannel(object):
            def close(self):
                self.closed = True
        zombie = DummyChannel()
        zombie.last_activity = 0
        zombie.running_tasks = False
        inst.active_channels[100] = zombie
        inst.maintenance(10000)
        self.assertEqual(zombie.will_close, True)

class DummySock(object):
    accepted = False
    blocking = False
    def __init__(self, toraise=None, acceptresult=(None, None)):
        self.toraise = toraise
        self.acceptresult = acceptresult
        self.opts = []
    def accept(self):
        if self.toraise:
            raise self.toraise
        self.accepted = True
        return self.acceptresult
    def setblocking(self, x):
        self.blocking = True
    def fileno(self):
        return 10
    def getpeername(self):
        return '127.0.0.1'
    def setsockopt(self, *arg):
        self.opts.append(arg)
    def getsockopt(self, *arg):
        return 1
    def listen(self, num):
        self.listened = num
    def getsockname(self):
        return '127.0.0.1', 80

class DummyTaskDispatcher(object):
    def __init__(self):
        self.tasks = []
    def add_task(self, task):
        self.tasks.append(task)

class DummyTask(object):
    serviced = False
    start_response_called = False
    wrote_header = False
    status = '200 OK'
    def __init__(self):
        self.response_headers = {}
        self.written = ''
    def service(self): # pragma: no cover
        self.serviced = True

class DummyAdj:
    connection_limit = 1
    log_socket_errors = True
    socket_options = [('level', 'optname', 'value')]
    cleanup_interval = 900
    channel_timeout= 300
    
    

