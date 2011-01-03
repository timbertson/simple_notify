import unittest
import tempfile
import shutil
import os
import time

import simple_notify
from simple_notify import Event

class Monitor():
	"""
	adds a watch, and adds all its events to a list.
	event retrieval is delayed by 0.1s, to ensure inotify
	callbacks have had a chance to fire
	"""
	def __init__(self, base, **kw):
		self._events = []
		self.base = base
		self.watcher = simple_notify.watch(base, callback=self.on_change, **kw)
		self.sleep_time = kw.get('latency',0.01)
	
	def _sleep(self):
		time.sleep(self.sleep_time * 2)

	def clear(self):
		self._sleep()
		print "dropping events: %r" % (self._events,)
		self._events = []
	
	@property
	def events(self):
		self._sleep()
		return self._events

	@property
	def event_types(self):
		return map(lambda x: x.event, self.events)
	
	@property
	def changed_paths(self):
		return list(sorted(set(map(lambda x: x.path, self.events))))

	def on_change(self, event):
		self._events.append(event)
	
	def stop(self):
		self.watcher.stop()

class BaseTest(unittest.TestCase):
	"""
	basic test class - maintains a temp-dir for the duration of the test,
	and provides utility methods for messing with that directory
	"""
	def setUp(self):
		self.base = tempfile.mkdtemp()
	
	def tearDown(self):
		self.monitor.stop()
		shutil.rmtree(self.base)

	def touch(self, path):
		with open(self.fullpath(path), 'w') as f:
			f.write("")
	
	def mkdir(self, path):
		os.mkdir(self.fullpath(path))
	
	def rm(self, path):
		path = self.fullpath(path)
		if os.path.isdir(path):
			shutil.rmtree(path)
		else:
			os.remove(path)
	
	def fullpath(self, path):
		return os.path.join(self.base, path)

	def mv(self, src, dest):
		src, dest = map(self.fullpath, (src, dest))
		os.rename(src, dest)
	

class SimpleEventsTest(BaseTest):
	"""test one level (non-recursive) cases"""
	def setUp(self):
		super(type(self), self).setUp()
		self.monitor = Monitor(self.base)
	
	def test_should_detect_a_new_file(self):
		self.touch("some_file")
		try:
			# this shouldn't be the case, but is acceptable
			# (I don't know why this case specifically generates two events...)
			self.assertEquals(self.monitor.events, [
				Event(base="", event=Event.ADDED, exists=True, name="some_file", is_dir=False),
				Event(base="", event=Event.MODIFIED, exists=True, name="some_file", is_dir=False)
			])
		except AssertionError:
			# this is ideal:
			self.assertEquals(self.monitor.events, [
				Event(base="", event=Event.ADDED, exists=True, name="some_file", is_dir=False),
			])
	
	def test_should_detect_a_modified_file(self):
		self.touch("some_file")
		self.monitor.clear()

		self.touch("some_file")
		self.assertEquals(self.monitor.events, [Event(base="", event=Event.MODIFIED, exists=True, name="some_file", is_dir=False)])
	
	def test_should_detect_a_deleted_file(self):
		self.touch("f")
		self.monitor.clear()
		self.rm("f")
		
		self.assertEquals(self.monitor.events, [simple_notify.Event(base="", event=simple_notify.Event.REMOVED, exists=False, name="f", is_dir=False)])

	def test_should_detect_a_deleted_dir(self):
		self.mkdir("d")
		self.monitor.clear()
		self.rm("d")
		
		self.assertEquals(self.monitor.events, [simple_notify.Event(base="", event=simple_notify.Event.REMOVED, exists=False, name="d", is_dir=True)])

	def test_should_detect_a_file_move(self):
		self.touch("a")
		self.monitor.clear()
		self.mv("a", "b")
		
		self.assertEquals(self.monitor.events, [
			simple_notify.Event(base="", event=simple_notify.Event.MOVED_FROM, exists=False, name="a", is_dir=True),
			simple_notify.Event(base="", event=simple_notify.Event.MOVED_TO, exists=True, name="b", is_dir=True)
			])

class NestedTest(BaseTest):
	"""cases involving multiple levels of directories"""
	def setUp(self):
		super(type(self), self).setUp()
		self.mkdir("nested")
		self.monitor = Monitor(self.base, ignore_modifications=False)

	def test_should_detect_events_to_a_nested_dir(self):
		self.mkdir("nested/dir")
		self.assertEquals(self.monitor.events, [simple_notify.Event(base="nested", event=simple_notify.Event.ADDED, exists=True, name="dir", is_dir=True)])

	def test_should_detect_events_to_a_nested_file(self):
		self.touch("nested/file")
		try:
			# this shouldn't be the case, but is acceptable
			# (I don't know why this case specifically generates two events...)
			self.assertEquals(self.monitor.events, [
				simple_notify.Event(base="nested", event=simple_notify.Event.ADDED, exists=True, name="file", is_dir=False),
				simple_notify.Event(base="nested", event=simple_notify.Event.MODIFIED, exists=True, name="file", is_dir=False)
			])
		except AssertionError:
			# this is ideal:
			self.assertEquals(self.monitor.events, [simple_notify.Event(base="nested", event=simple_notify.Event.ADDED, exists=True, name="file", is_dir=False)])

	def test_should_detect_a_file_move_between_directories(self):
		self.mkdir("dest")
		self.touch("nested/file")
		self.monitor.clear()

		self.mv("nested/file", "dest/file2")
		self.assertEquals(self.monitor.events, [
			simple_notify.Event(base="nested", event=simple_notify.Event.MOVED_FROM, exists=False, name="file", is_dir=False),
			simple_notify.Event(base="dest", event=simple_notify.Event.MOVED_TO, exists=True, name="file2", is_dir=False),
		])
	
	def test_should_only_mention_directories_even_if_children__move(self):
		self.touch("nested/file")
		self.monitor.clear()

		self.mv("nested", "dest")
		self.assertEquals(self.monitor.events, [
			simple_notify.Event(base="", event=simple_notify.Event.MOVED_FROM, exists=False, name="nested", is_dir=True),
			simple_notify.Event(base="", event=simple_notify.Event.MOVED_TO, exists=True, name="dest", is_dir=True),
		])

class IgnoreNodificationTest(BaseTest):
	"""testing ignored mode operation"""
	def setUp(self):
		super(type(self), self).setUp()
		self.monitor = Monitor(self.base, ignore_modifications=True)
	
	def test_should_not_track_modifications(self):
		self.touch("some_file")
		self.touch("some_file")
		self.assertEquals(self.monitor.events, [simple_notify.Event(base="", event=simple_notify.Event.ADDED, exists=True, name="some_file", is_dir=True)])

class CombineQuickEventsTest(BaseTest):
	def setUp(self):
		super(type(self), self).setUp()
		self.latency = 0.2
		self.monitor = Monitor(self.base, latency=self.latency)
	
	def sleep(self):
		time.sleep(self.latency * 2)
	
	def test_should_combine_delete_and_add_events_into_modification(self):
		self.touch("some_file")
		self.monitor.clear()
		self.rm("some_file")
		self.touch("some_file")
		self.assertEquals(self.monitor.event_types, [simple_notify.Event.MODIFIED])

	def test_should_combine_add_and_remove_events_into_nothing(self):
		self.touch("some_file")
		self.rm("some_file")
		self.assertEquals(self.monitor.events, [])

	def test_should_not_combine_events_that_happen_more_than__latency__seconds_apart(self):
		print repr(os.listdir(self.base))
		self.touch("some_file")
		self.sleep()
		self.rm("some_file")
		self.assertEquals(self.monitor.event_types, [simple_notify.Event.ADDED, simple_notify.Event.REMOVED])
	
class SimplificationTest(unittest.TestCase):
	def event(self, event):
		return simple_notify.Event(base="base", event=event, exists=True, name="name", is_dir=False)
	def combine(self, first_type, second_type):
		return self.event(first_type)._combines_with(self.event(second_type))

	def test_should_combine_create_and_remove(self):
		self.assertEquals(self.combine(Event.ADDED, Event.REMOVED), None)

	def test_should_combine_remove_and_create(self):
		self.assertEquals(self.combine(Event.REMOVED, Event.ADDED), Event.MODIFIED)

	def test_should_combine_multiple_modifications(self):
		self.assertEquals(self.combine(Event.MODIFIED, Event.MODIFIED), Event.MODIFIED)

