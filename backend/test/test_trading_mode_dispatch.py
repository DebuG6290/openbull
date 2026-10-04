"""Pure dispatch contract tests; no broker, database or credentials are needed.

Compile the production helper from its AST rather than importing service startup
dependencies. Only the mode reader is mocked; callback behavior is real async code.
"""
import ast
from pathlib import Path
import unittest
from unittest.mock import AsyncMock


class DispatchContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        source = Path(__file__).resolve().parents[1] / 'services' / 'trading_mode_service.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        helper = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'dispatch_by_mode')
        future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
        isolated = ast.fix_missing_locations(ast.Module(body=[future, helper], type_ignores=[]))
        self.mode = AsyncMock(return_value='sandbox')
        namespace = {'get_trading_mode': self.mode, 'TRADING_MODE_SANDBOX': 'sandbox'}
        exec(compile(isolated, str(source), 'exec'), namespace)
        self.dispatch = namespace['dispatch_by_mode']
        self.live = AsyncMock(return_value='live-result')
        self.sandbox = AsyncMock(return_value='sandbox-result')

    async def test_missing_sandbox_callback_never_calls_live(self):
        with self.assertRaisesRegex(ValueError, 'Sandbox mode requires a sandbox callback'):
            await self.dispatch(self.live, None, 'order', user_id=7)
        self.live.assert_not_awaited()

    async def test_sandbox_forwards_arguments_and_result(self):
        result = await self.dispatch(self.live, self.sandbox, 'order', user_id=7)
        self.assertEqual(result, 'sandbox-result')
        self.sandbox.assert_awaited_once_with('order', user_id=7)
        self.live.assert_not_awaited()

    async def test_live_without_sandbox_callback_still_works(self):
        self.mode.return_value = 'live'
        self.assertEqual(await self.dispatch(self.live, None, 'order'), 'live-result')
        self.live.assert_awaited_once_with('order')

    async def test_live_with_sandbox_callback_does_not_call_sandbox(self):
        self.mode.return_value = 'live'
        self.assertEqual(await self.dispatch(self.live, self.sandbox), 'live-result')
        self.sandbox.assert_not_awaited()

    async def test_sandbox_callback_failure_does_not_fall_back_to_live(self):
        self.sandbox.side_effect = RuntimeError('simulation failed')
        with self.assertRaisesRegex(RuntimeError, 'simulation failed'):
            await self.dispatch(self.live, self.sandbox)
        self.live.assert_not_awaited()

    async def test_mode_reader_failure_does_not_dispatch(self):
        self.mode.side_effect = RuntimeError('mode unavailable')
        with self.assertRaisesRegex(RuntimeError, 'mode unavailable'):
            await self.dispatch(self.live, self.sandbox)
        self.live.assert_not_awaited()
        self.sandbox.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()

