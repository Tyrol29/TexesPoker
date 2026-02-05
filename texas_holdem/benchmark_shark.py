"""
鲨鱼AI强度测试 - 6AI自动对战100手
统计鲨鱼AI的胜率和盈利能力
"""

import sys
import random
import io
from contextlib import redirect_stdout
from typing import List, Dict, Any

sys.path.insert(0, 'd:\\workspace\\Texes')

from texas_holdem.game.game_engine import GameEngine
from texas_holdem.game.game_state import GameState
from texas_holdem.ai.ai_engine import AIEngine
from texas_holdem.ai.shark_ai import SharkAI
from texas_holdem.utils.constants import INITIAL_CHIPS, GameState as GS


class SilentGameRunner:
    """静默运行游戏，不输出到控制台"""
    
    def __init__(self, num_hands: int = 100):
        self.num_hands = num_hands
        self.ai_engine = AIEngine()
        self.shark_ai = SharkAI()
        
        # 统计结果
        self.shark_stats = {
            'hands_played': 0,
            'hands_won': 0,
            'showdowns': 0,
            'showdown_wins': 0,
            'wins_without_showdown': 0,
            'final_chips': 0,
            'profit': 0,
            'vpip_count': 0,
            'pfr_count': 0,
            'folds': 0,
            'eliminated': False,
            'eliminated_at': 0,
            'final_rank': 0,
        }
        
        # 每手牌的结果记录
        self.hand_results = []
        
    def setup_game(self):
        """设置游戏 - 6个AI玩家"""
        player_names = [
            '电脑1号[鲨鱼]',
            '电脑2号[松凶]', 
            '电脑3号[紧凶]',
            '电脑4号[紧弱]',
            '电脑5号[松弱]',
            '电脑6号[紧凶]'
        ]
        
        self.engine = GameEngine(player_names, INITIAL_CHIPS)
        
        # 设置AI风格
        style_map = {
            '紧凶': 'TAG',
            '松凶': 'LAG',
            '紧弱': 'LAP', 
            '松弱': 'LP',
            '鲨鱼': 'SHARK'
        }
        
        for player in self.engine.players:
            player.is_ai = True
            if '[' in player.name and ']' in player.name:
                cn_style = player.name.split('[')[1].split(']')[0]
                player.ai_style = style_map.get(cn_style, 'LAG')
        
        # 初始化鲨鱼AI
        self.shark_ai.initialize_opponents(self.engine.players)
        
        # 获取鲨鱼初始筹码
        shark = self._get_shark()
        if shark:
            self.shark_start_chips = shark.chips
            
    def _get_shark(self):
        """获取鲨鱼玩家"""
        for p in self.engine.players:
            if getattr(p, 'ai_style', '') == 'SHARK':
                return p
        return None
    
    def _get_ai_action(self, player, betting_round):
        """获取AI行动"""
        from texas_holdem.utils.constants import Action
        
        game_state = betting_round.game_state
        hole_cards = player.hand.cards if player.hand else []
        community_cards = game_state.table.community_cards
        
        hand_strength = self.ai_engine.evaluate_hand_strength(hole_cards, community_cards)
        win_prob = hand_strength
        
        amount_to_call = betting_round.get_amount_to_call(player)
        total_pot = game_state.table.total_pot
        pot_odds = self.ai_engine.calculate_pot_odds(total_pot, amount_to_call) if amount_to_call > 0 else 0
        ev = self.ai_engine.calculate_expected_value(hand_strength, pot_odds, amount_to_call, total_pot)
        
        # 鲨鱼AI使用自己的决策
        if player.ai_style == 'SHARK':
            action, amount = self.shark_ai.get_action(
                player, betting_round, hand_strength, win_prob, pot_odds, ev
            )
        else:
            # 其他AI使用标准引擎
            action, amount = self.ai_engine.get_action(
                player, betting_round, hand_strength, win_prob, pot_odds, ev
            )
        
        return action, amount
    
    def run_hand(self, hand_num: int) -> bool:
        """运行一手牌"""
        try:
            # 检查鲨鱼是否被淘汰
            shark = self._get_shark()
            if not shark or shark.chips <= 0:
                if not self.shark_stats['eliminated']:
                    self.shark_stats['eliminated'] = True
                    self.shark_stats['eliminated_at'] = hand_num
                return False
            
            # 开始新一手
            self.engine.start_new_hand()
            self.shark_stats['hands_played'] += 1
            
            # 记录鲨鱼初始筹码
            shark_start_chips = shark.chips if shark else 0
            
            # 运行翻牌前
            if not self._run_betting_round('preflop'):
                self._check_winner(shark_start_chips)
                return True
            
            # 翻牌圈
            active = len([p for p in self.engine.players if p.is_active])
            if active > 1:
                self.engine.deal_flop()
                self.engine.game_state.advance_stage()
                if not self._run_betting_round('flop'):
                    self._check_winner(shark_start_chips)
                    return True
            
            # 转牌圈
            active = len([p for p in self.engine.players if p.is_active])
            if active > 1:
                self.engine.deal_turn()
                self.engine.game_state.advance_stage()
                if not self._run_betting_round('turn'):
                    self._check_winner(shark_start_chips)
                    return True
            
            # 河牌圈
            active = len([p for p in self.engine.players if p.is_active])
            if active > 1:
                self.engine.deal_river()
                self.engine.game_state.advance_stage()
                if not self._run_betting_round('river'):
                    self._check_winner(shark_start_chips)
                    return True
            
            # 摊牌
            self._resolve_showdown(shark_start_chips)
            return True
            
        except Exception as e:
            return False
    
    def _run_betting_round(self, street: str) -> bool:
        """运行下注轮"""
        from texas_holdem.game.betting import BettingRound
        
        game_state = self.engine.game_state
        betting_round = BettingRound(game_state)
        
        max_actions = 100
        action_count = 0
        
        while not game_state.is_betting_round_complete() and action_count < max_actions:
            current_player = game_state.get_current_player()
            if not current_player or not current_player.is_active:
                game_state.move_to_next_player()
                continue
            
            # 获取行动
            action, amount = self._get_ai_action(current_player, betting_round)
            if action is None:
                game_state.move_to_next_player()
                continue
            
            # 记录鲨鱼数据
            shark = self._get_shark()
            if shark and current_player.name == shark.name:
                action_str = str(action).lower().replace('action.', '')
                if street == 'preflop' and action_str in ['raise', 'call', 'bet']:
                    self.shark_stats['vpip_count'] += 1
                if street == 'preflop' and action_str == 'raise':
                    self.shark_stats['pfr_count'] += 1
                if action_str == 'fold':
                    self.shark_stats['folds'] += 1
            
            # 更新鲨鱼AI追踪
            if current_player.ai_style != 'SHARK':
                action_str = str(action).lower().replace('action.', '')
                self.shark_ai.update_after_action(
                    current_player.name, action_str, street
                )
            
            # 执行行动
            success, msg, bet_amount = betting_round.process_action(current_player, action, amount)
            if not success:
                game_state.move_to_next_player()
                continue
            
            action_count += 1
            
            # 检查是否只剩一个玩家
            active_players = [p for p in self.engine.players if p.is_active]
            if len(active_players) <= 1:
                return False
        
        # 收集下注
        betting_round.collect_bets()
        game_state.advance_stage()
        return True
    
    def _check_winner(self, shark_start_chips: int):
        """检查赢家（不摊牌）"""
        shark = self._get_shark()
        if not shark:
            return
        
        active = [p for p in self.engine.players if p.is_active]
        if len(active) == 1 and active[0].name == shark.name:
            self.shark_stats['hands_won'] += 1
            self.shark_stats['wins_without_showdown'] += 1
    
    def _resolve_showdown(self, shark_start_chips: int):
        """摊牌结算"""
        from texas_holdem.core.evaluator import PokerEvaluator
        
        game_state = self.engine.game_state
        active_players = [p for p in self.engine.players if p.is_active]
        
        if len(active_players) == 0:
            return
        
        if len(active_players) == 1:
            winner = active_players[0]
            win_amount = game_state.table.total_pot
            winner.chips += win_amount
            
            shark = self._get_shark()
            if shark and winner.name == shark.name:
                self.shark_stats['hands_won'] += 1
                self.shark_stats['wins_without_showdown'] += 1
            return
        
        # 比较牌力
        community_cards = game_state.table.community_cards
        if len(community_cards) < 5:
            return
        
        best_rank = float('inf')
        winners = []
        
        for player in active_players:
            if player.hand and len(player.hand.cards) == 2:
                all_cards = player.hand.cards + community_cards
                try:
                    rank, values = PokerEvaluator.evaluate_hand(all_cards)
                    if rank < best_rank:
                        best_rank = rank
                        winners = [player]
                    elif rank == best_rank:
                        winners.append(player)
                except:
                    continue
        
        # 分配底池
        if winners:
            win_amount = game_state.table.total_pot // len(winners)
            for winner in winners:
                winner.chips += win_amount
                
                shark = self._get_shark()
                if shark and winner.name == shark.name:
                    self.shark_stats['hands_won'] += 1
                    self.shark_stats['showdown_wins'] += 1
                    self.shark_stats['showdowns'] += 1
    
    def run_benchmark(self) -> Dict:
        """运行完整测试"""
        print(f"\n{'='*60}")
        print(f"  鲨鱼AI强度测试 - {self.num_hands}手牌")
        print(f"{'='*60}\n")
        
        self.setup_game()
        
        # 使用StringIO抑制输出
        f = io.StringIO()
        with redirect_stdout(f):
            for hand_num in range(1, self.num_hands + 1):
                if hand_num % 10 == 0:
                    print(f"  进度: {hand_num}/{self.num_hands}")
                
                if not self.run_hand(hand_num):
                    if self.shark_stats['eliminated']:
                        print(f"\n  鲨鱼AI在第{hand_num}手牌被淘汰！")
                        break
        
        # 计算最终结果
        self._calculate_final_results()
        
        return self.shark_stats
    
    def _calculate_final_results(self):
        """计算最终结果"""
        shark = self._get_shark()
        if shark:
            self.shark_stats['final_chips'] = shark.chips
            self.shark_stats['profit'] = shark.chips - self.shark_start_chips
        
        # 计算排名
        all_players = [(p.name, p.chips) for p in self.engine.players]
        all_players.sort(key=lambda x: x[1], reverse=True)
        
        for rank, (name, chips) in enumerate(all_players, 1):
            if '鲨鱼' in name or 'SHARK' in name:
                self.shark_stats['final_rank'] = rank
                break
        
        # 计算VPIP/PFR
        if self.shark_stats['hands_played'] > 0:
            self.shark_stats['vpip'] = self.shark_stats['vpip_count'] / self.shark_stats['hands_played'] * 100
            self.shark_stats['pfr'] = self.shark_stats['pfr_count'] / self.shark_stats['hands_played'] * 100
    
    def print_report(self):
        """打印测试报告"""
        print(f"\n{'='*60}")
        print(f"  鲨鱼AI测试报告")
        print(f"{'='*60}\n")
        
        s = self.shark_stats
        hands = s['hands_played']
        
        print(f"  测试手牌数:     {hands}/{self.num_hands}")
        print(f"  最终排名:       {s['final_rank']}/6")
        print(f"  初始筹码:       {self.shark_start_chips}")
        print(f"  最终筹码:       {s['final_chips']}")
        print(f"  盈亏:           {s['profit']:+d}")
        print(f"  胜率:           {s['hands_won']}/{hands} ({100*s['hands_won']/max(1,hands):.1f}%)")
        print(f"\n  --- 详细数据 ---")
        print(f"  VPIP:           {s.get('vpip', 0):.1f}%")
        print(f"  PFR:            {s.get('pfr', 0):.1f}%")
        print(f"  摊牌次数:       {s['showdowns']}")
        print(f"  摊牌胜率:       {100*s['showdown_wins']/max(1,s['showdowns']):.1f}%" if s['showdowns'] > 0 else "  摊牌胜率:       N/A")
        print(f"  不摊牌胜:       {s['wins_without_showdown']}")
        print(f"  总弃牌:         {s['folds']}")
        print(f"  是否淘汰:       {'是' if s['eliminated'] else '否'}")
        if s['eliminated']:
            print(f"  淘汰于手牌:     {s['eliminated_at']}")
        
        # 对手分析
        print(f"\n  --- 对手分析 ---")
        print(f"  {self.shark_ai.get_opponent_summary()}")
        
        print(f"\n{'='*60}\n")


def run_multiple_benchmarks(num_tests: int = 3, num_hands: int = 100):
    """运行多次测试取平均"""
    print(f"\n{'#'*60}")
    print(f"#  鲨鱼AI强度测试 - {num_tests}轮 x {num_hands}手牌")
    print(f"{'#'*60}\n")
    
    all_results = []
    
    for test_num in range(1, num_tests + 1):
        print(f"\n{'#'*60}")
        print(f"#  第 {test_num}/{num_tests} 轮测试")
        print(f"{'#'*60}")
        
        runner = SilentGameRunner(num_hands=num_hands)
        result = runner.run_benchmark()
        runner.print_report()
        
        all_results.append(result)
    
    # 汇总
    print(f"\n{'#'*60}")
    print(f"#  汇总报告 ({num_tests}轮测试)")
    print(f"{'#'*60}\n")
    
    avg_hands = sum(r['hands_played'] for r in all_results) / num_tests
    avg_profit = sum(r['profit'] for r in all_results) / num_tests
    avg_wins = sum(r['hands_won'] for r in all_results) / num_tests
    avg_vpip = sum(r.get('vpip', 0) for r in all_results) / num_tests
    avg_pfr = sum(r.get('pfr', 0) for r in all_results) / num_tests
    
    eliminations = sum(1 for r in all_results if r['eliminated'])
    avg_rank = sum(r['final_rank'] for r in all_results) / num_tests
    
    print(f"  平均手牌数:     {avg_hands:.1f}")
    print(f"  平均盈亏:       {avg_profit:+.0f}")
    print(f"  平均胜场:       {avg_wins:.1f}")
    print(f"  平均VPIP:       {avg_vpip:.1f}%")
    print(f"  平均PFR:        {avg_pfr:.1f}%")
    print(f"  平均排名:       {avg_rank:.1f}/6")
    print(f"  淘汰次数:       {eliminations}/{num_tests}")
    
    # 评估
    print(f"\n  --- 评估 ---")
    if avg_profit > 500 and eliminations == 0:
        print(f"  [强] 鲨鱼AI表现优秀！")
    elif avg_profit > 0:
        print(f"  [良] 鲨鱼AI表现尚可")
    elif eliminations < num_tests / 2:
        print(f"  [中] 鲨鱼AI表现一般，需要调整")
    else:
        print(f"  [弱] 鲨鱼AI表现不佳，需要大幅改进")
    
    print(f"\n{'#'*60}\n")
    
    return all_results


if __name__ == '__main__':
    # 运行3轮测试，每轮100手牌
    results = run_multiple_benchmarks(num_tests=3, num_hands=100)
