import Queue as queue
import os
import logging
import threading
logger = logging.getLogger(__name__)

from pyinotify import WatchManager, ThreadedNotifier, ProcessEvent
from pyinotify import IN_DELETE, IN_CREATE, IN_MOVED_FROM, IN_MOVED_TO, IN_CLOSE_WRITE
EVENT_MASK = IN_DELETE | IN_CREATE | IN_MOVED_TO | IN_MOVED_FROM
EVENT_MASK_WITH_MODIFICATIONS = EVENT_MASK | IN_CLOSE_WRITE

class Watch(object):
	def __init__(self, path, callback, ignore_modifications=False, latency=None):
		self.event_mask = EVENT_MASK if ignore_modifications else EVENT_MASK_WITH_MODIFICATIONS
		self._dir_queue = queue.Queue()
		self._root = os.path.realpath(path)

		self._watch_manager = WatchManager()

		self._processor = FileProcessEvent(directory_queue=self._dir_queue, root=self._root, callback=callback, latency=latency)
		self._notifier = ThreadedNotifier(self._watch_manager, self._processor)

		self._notifier.name = "[inotify] notifier"
		self._notifier.daemon = True
		self._notifier.start()

		self._watch_manager.add_watch(path, self.event_mask, rec=True, auto_add=True)
	
	def stop(self):
		self._notifier.stop()
		self._processor.stop()
	
class Event(object):
	MOVED_TO = 'MOVED_TO'
	MOVED_FROM = 'MOVED_FROM'
	MODIFIED = 'MODIFIED'
	ADDED = 'ADDED'
	REMOVED = 'REMOVED'

	def __init__(self, base, event, exists, name, is_dir):
		self.base = base
		self.name = name
		self.event = event
		self.exists = exists
		self.is_dir=is_dir
	
	def __eq__(self, other):
		if not isinstance(other, type(self)): return False
		attrs = ['base', 'name', 'event', 'exists']
		return map(lambda a: getattr(self, a) , attrs) == \
		       map(lambda a: getattr(other, a), attrs)
	
	def __repr__(self):
		return "<# %s %s at %s >"% (
				self.event, "dir" if self.is_dir else "file", self.path)
	
	_simplifications = {
		(REMOVED, ADDED): MODIFIED,
		(ADDED, REMOVED): None,
		(ADDED, MODIFIED): ADDED,
		(MODIFIED, MODIFIED): MODIFIED,
	}
	def _combines_with(self, later_event):
		if self.path == later_event.path:
			types = (self.event, later_event.event)
			return self._simplifications.get(types, False)
		return False
	
	__str__ = __repr__
	
	@property
	def path(self):
		return os.path.join(self.base, self.name or '')

def handler(which, exists):
	def handle_event(self, event):
		event_path = self.relative_path(event.path)
		is_dir = self.is_dir(event)
		self.on_change(Event(base=event_path, name=event.name, event=which, exists=exists, is_dir=is_dir))
	return handle_event

class FileProcessEvent(ProcessEvent):
	def __init__(self, directory_queue, root, callback, latency):
		self.latency = latency
		self._dir_queue = directory_queue
		self._root = root
		self._event_queue = queue.Queue()
		if self.latency:
			self.callback = callback
			self.callback_trigger = threading.Thread(target=self.collect_events, name="filesystem event collector")
			self.callback_trigger.daemon=True
			self.callback_trigger.start()
		else:
			self.on_change = callback
	
	def stop(self):
		try:
			self.callback_trigger.stop()
		except AttributeError:
			pass

	def on_change(self, event):
		self._event_queue.put(event)
	
	def collect_events(self):
		while True:
			events = []
			try:
				event = self._event_queue.get() # block until first event in group
				events.append(event)
				while len(events) < 100:
					# collect events until latency is up, or too many events have occurred
					event = self._event_queue.get(timeout=self.latency)
					events.append(event)
			except queue.Empty:
				pass

			simplified_events = self.simplify_events(events)
			map(self.callback, simplified_events)

	def simplify_events(self, remaining_events):
		simplified_events = []
		while remaining_events:
			event = remaining_events.pop(0)
			keep_simplifying = True
			while keep_simplifying:
				for index, future_event in enumerate(remaining_events):
					combination = event._combines_with(future_event)
					if combination is not False:
						del remaining_events[index]
						if combination is None:
							keep_simplifying = False
						else:
							event.event = combination
						break
				else:
					simplified_events.append(event)
					keep_simplifying = False
		return simplified_events
	
	def is_dir(self, event):
		if hasattr(event, "dir"):
			return event.dir
		else:
			return event.is_dir
	
	def relative_path(self, path):
		if path.startswith(self._root):
			return path[len(self._root):].lstrip(os.path.sep)
		else:
			logger.warn("non-relative path encountered: %s" % (path,))
		return path

	process_IN_CLOSE_WRITE = handler(Event.MODIFIED, True)
	process_IN_CREATE = handler(Event.ADDED, True)
	process_IN_DELETE = handler(Event.REMOVED, False)
	process_IN_MOVED_FROM = handler(Event.MOVED_FROM, False)
	process_IN_MOVED_TO = handler(Event.MOVED_TO, True)

watch = Watch

if __name__ == '__main__':
	def on_change(event):
		print event.name, event.event, event.exists
	watch('.', on_change)
	raw_input()
