"""Synthetic continuation checks; no live model or learning-outcome evaluation."""
from pathlib import Path
import tempfile
import unittest

from test_learning_app import FILES, archive, wait_ready
from test_learning_workspace import Tutor
from exampleproof.learn_server import LearningApp


class FollowupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.client = Tutor()
        self.app = LearningApp(Path(temp.name)/'data', 'ollama', 'fixture', lambda: self.client)
        self.addCleanup(self.app.pool.shutdown)
        self.record = wait_ready(self.app, self.app.create(name='Synthetic', goal='理解调用', level='beginner', upload=archive(FILES))['id'])
        self.ws = self.app.workspace
        self.view = self.ws.view(self.record['id'])
        self.base = {'route_id': self.view['route_id'], 'step_key': self.view['tasks'][0]['key'], 'intent': 'ask'}

    def prepare(self, **values):
        return self.ws.prepare(self.record['id'], self.base | {'question': '为什么这样调用？'} | values)

    def test_older_answer_is_in_bounded_context_and_followup_is_saved(self):
        first = self.prepare(question='第一条问题', use_ai=False)
        for index in range(6):
            self.prepare(question=f'后续问题 {index}', use_ai=False)
        preview = self.prepare(reply_to=first['id'])
        payload = preview['preview']
        self.assertEqual(payload['reply_to']['id'], first['id'])
        self.assertEqual(payload['reply_to']['question'], '第一条问题')
        self.assertEqual(len(payload['conversation']), 4)
        self.assertEqual(payload['conversation'][0]['question'], '第一条问题')
        self.assertEqual(payload['conversation'][-1]['question'], '后续问题 5')
        self.assertEqual(self.client.calls, 0)
        saved = self.prepare(reply_to=first['id'], use_ai=False)
        discussion = next(d for d in self.ws.view(self.record['id'])['discussions'] if d['id'] == saved['id'])
        self.assertEqual(discussion['reply_to'], first['id'])

    def test_cannot_follow_up_another_step_or_an_exercise(self):
        first = self.prepare(use_ai=False)
        with self.assertRaises(ValueError):
            self.prepare(step_key=self.view['tasks'][1]['key'], reply_to=first['id'])
        exercise = self.prepare(intent='feedback', exercise_id='explain', use_ai=False)
        with self.assertRaises(ValueError):
            self.prepare(reply_to=exercise['id'])
        for invalid in ('missing', [], {}, 1):
            with self.assertRaises(ValueError):
                self.prepare(reply_to=invalid)
        self.assertEqual(self.client.calls, 0)

    def test_pending_draft_can_be_restored_without_exposing_model_payload(self):
        parent = self.prepare(use_ai=False)
        request = self.prepare(reply_to=parent['id'], question='token="PRIVATE_QUESTION" 请解释')
        public = self.ws.status(self.record['id'], request['id'])
        self.assertEqual(public['draft']['reply_to'], parent['id'])
        self.assertEqual(public['draft']['intent'], 'ask')
        self.assertNotIn('PRIVATE_QUESTION', public['draft']['question'])
        self.assertNotIn('payload', public)
        self.assertNotIn('binding', public)


if __name__ == '__main__':
    unittest.main()
