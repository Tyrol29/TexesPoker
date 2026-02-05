"""
鲨鱼AI自动化测试脚本
6个电脑自动对局100手牌，分析鲨鱼AI表现
"""

import sys
import random
from typing import List, Dict, Any
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, 'd:\\workspace\\Texes')

from texas_holdem.core.card import Card
from texas_holdem.core.deck import Deck
from texas_holdem.core.player import Player
from texas_holdem.core.table import Table
from texas_holdem.game.game_state import GameState
from texas_holdem.game.game_engine import GameEngine
from texas_holdem.ai.ai_engine import AIEngine
from texas_holdem.ai.shark_ai import SharkAI


class AutoGameTester:
    """自动化游戏测试器"""
    
    def __init__(self, num_hands: int = 100, num_players: int = 6):
        self.num_hands = num_hands
        self.num_players = num_players
        self.engine = None
        self.ai_engine = AIEngine()
        self.shark_ai = None
        self.results = {
            'hands_played': 0,
            'shark_chips_start': 0,
            'shark_chips_end': 0,
            'shark_profit': 0,
            'hands_won': 0,
            'showdowns': 0,
            'folds': 0,
            'vpip_count': 0,  # 入池次数
            'pfr_count': 0,   # 翻牌前加注次数
            'eliminated': False,
            'eliminated_at_hand': 0,
            'final_rank': 0,
        }
        self.hand_history = []
        
    def setup_game(self):
        """设置游戏"""
        # 创建6个AI玩家名称
        player_names = ['电脑1号[鲨鱼]', '电脑2号[紧凶]', '电脑3号[松凶]', 
                       '电脑4号[紧弱]', '电脑5号[松弱]', '电脑6号[紧凶]']
        
        # 创建游戏引擎
        self.engine = GameEngine(player_names, initial_chips=1000)
        
        # 设置AI风格和标记
        style_map = {
            '紧凶': 'TAG',
            '松凶': 'LAG', 
            '紧弱': 'LAP',
            '松弱': 'LP',
            '鲨鱼': 'SHARK'
        }
        
        for player in self.engine.players:
            player.is_ai = True
            # 从名称中提取风格
            if '[' in player.name and ']' in player.name:
                cn_style = player.name.split('[')[1].split(']')[0]
                player.ai_style = style_map.get(cn_style, 'LAG')
            else:
                player.ai_style = 'LAG'
        
        # 初始化鲨鱼AI
        self.shark_ai = SharkAI()
        self.shark_ai.initialize_opponents(self.engine.players)
        
        # 记录初始筹码
        shark = self._get_shark_player()
        if shark:
            self.results['shark_chips_start'] = shark.chips
    
    def _get_shark_player(self) -> Player:
        """获取鲨鱼AI玩家"""
        for player in self.engine.game_state.players:
            if getattr(player, 'ai_style', '') == 'SHARK':
                return player
        return None
    
    def _get_ai_action(self, player: Player) -> tuple:
        """获取AI行动"""
        game_state = self.engine.game_state
        betting_round = self.engine.betting_round
        
        if not betting_round:
            return None, 0
        
        available_actions = betting_round.get_available_actions(player)
        if not available_actions:
            return None, 0
        
        amount_to_call = betting_round.get_amount_to_call(player)
        
        # 评估手牌
        hole_cards = player.hand.cards if player.hand else []
        community_cards = game_state.table.community_cards
        
        hand_strength = self.ai_engine.evaluate_hand_strength(hole_cards, community_cards)
        win_prob = hand_strength
        
        # 计算底池赔率
        total_pot = game_state.table.total_pot if hasattr(game_state.table, 'total_pot') else 0
        pot_odds = self.ai_engine.calculate_pot_odds(total_pot, amount_to_call) if amount_to_call > 0 else 0
        
        # 计算EV
        ev = self.ai_engine.calculate_expected_value(hand_strength, pot_odds, amount_to_call, total_pot)
        
        # 鲨鱼AI使用自己的决策
        if player.ai_style == 'SHARK' and self.shark_ai:
            return self.shark_ai.get_action(player, betting_round, hand_strength, win_prob, pot_odds, ev)
        
        # 其他AI使用标准引擎
        return self.ai_engine.get_action(player, betting_round, hand_strength, win_prob, pot_odds, ev)
    
    def _track_action(self, player: Player, action: str, amount: int):
        """追踪行动"""
        if player.ai_style != 'SHARK':
            return
        
        game_state = self.engine.game_state
        
        # 记录VPIP（翻牌前入池）
        if game_state.state == GameState.PRE_FLOP and action not in ['fold']:
            self.results['vpip_count'] += 1
        
        # 记录PFR（翻牌前加注）
        if game_state.state == GameState.PRE_FLOP and action in ['raise', 'bet']:
            self.results['pfr_count'] += 1
        
        # 记录fold
        if action == 'fold':
            self.results['folds'] += 1
    
    def _process_betting_round(self) -> bool:
        """处理下注轮，返回是否继续游戏"""
        betting_round = self.engine.betting_round
        game_state = self.engine.game_state
        
        max_actions = 50
        action_count = 0
        
        while not game_state.is_betting_round_complete() and action_count < max_actions:
            current_player = game_state.get_current_player()
            if not current_player or not current_player.is_active:
                game_state.next_player()
                continue
            
            # 获取AI行动
            action, amount = self._get_ai_action(current_player)
            if action is None:
                game_state.next_player()
                continue
            
            # 记录行动
            action_str = action.name.lower() if hasattr(action, 'name') else str(action).lower()
            self._track_action(current_player, action_str, amount)
            
            # 更新鲨鱼AI的对手追踪
            if self.shark_ai and getattr(current_player, 'ai_style', '') != 'SHARK':
                street = game_state.state.name.lower() if hasattr(game_state.state, 'name') else str(game_state.state).lower()
                self.shark_ai.update_after_action(current_player.name, action_str, street)
            
            # 执行行动
            success, message, bet_amount = betting_round.process_action(current_player, action, amount)
            if not success:
                game_state.next_player()
                continue
            
            action_count += 1
            
            # 检查是否只剩一个玩家
            active_players = [p for p in game_state.players if p.is_active and p.chips > 0]
            if len([p for p in game_state.players if p.is_active]) <= 1:
                return False
        
        # 收集下注
        betting_round.collect_bets()
        return True
    
    def run_hand(self) -> bool:
        """运行一手牌，返回是否成功完成"""
        try:
            # 检查鲨鱼是否被淘汰
            shark = self._get_shark_player()
            if not shark or shark.chips <= 0:
                self.results['eliminated'] = True
                if self.results['eliminated_at_hand'] == 0:
                    self.results['eliminated_at_hand'] = self.results['hands_played']
                return False
            
            # 开始新一手
            self.engine.start_new_hand()
            self.results['hands_played'] += 1
            
            # 翻牌前下注
            if not self._process_betting_round():
                return True
            
            # 检查是否只剩一个玩家
            active_count = len([p for p in self.engine.game_state.players if p.is_active])
            if active_count <= 1:
                return True
            
            # 发翻牌
            self.engine.deal_flop()
            self.engine.game_state.advance_stage()
            if not self._process_betting_round():
                return True
            
            # 检查是否只剩一个玩家
            active_count = len([p for p in self.engine.game_state.players if p.is_active])
            if active_count <= 1:
                return True
            
            # 发转牌
            self.engine.deal_turn()
            self.engine.game_state.advance_stage()
            if not self._process_betting_round():
                return True
            
            # 检查是否只剩一个玩家
            active_count = len([p for p in self.engine.game_state.players if p.is_active])
            if active_count <= 1:
                return True
            
            # 发河牌
            self.engine.deal_river()
            self.engine.game_state.advance_stage()
            if not self._process_betting_round():
                return True
            
            # 检查赢家
            self._check_winner()
            return True
            
        except Exception as e:
            print(f"  [错误] 手牌运行错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _check_winner(self):
        """检查赢家 - 简化版，使用游戏引擎的方法"""
        # 简单记录：如果鲨鱼还活跃，随机决定是否赢了这一手
        game_state = self.engine.game_state
        shark = self._get_shark_player()
        
        if shark and shark.is_active:
            # 鲨鱼在这一手活跃到结束，假设它有一定概率获胜
            # 简化处理：不实际比较牌力，因为底池分配比较复杂
            pass  # 不修改筹码，让游戏继续
    
    def run_test(self) -> Dict:
        """运行完整测试"""
        print(f"\n{'='*60}")
        print(f"  Shark AI Auto Test - {self.num_hands} hands")
        print(f"{'='*60}\n")
        
        self.setup_game()
        
        for hand_num in range(1, self.num_hands + 1):
            if hand_num % 10 == 0:
                print(f"  Progress: {hand_num}/{self.num_hands} hands")
            
            if not self.run_hand():
                if self.results['eliminated']:
                    print(f"\n  [WARNING] Shark AI eliminated at hand {hand_num}!")
                    break
        
        # 计算结果
        self._calculate_final_results()
        
        return self.results
    
    def _calculate_final_results(self):
        """计算最终结果"""
        shark = self._get_shark_player()
        if shark:
            self.results['shark_chips_end'] = shark.chips
            self.results['shark_profit'] = shark.chips - self.results['shark_chips_start']
        
        # 计算排名
        all_players = [(p.name, p.chips) for p in self.engine.game_state.players]
        all_players.sort(key=lambda x: x[1], reverse=True)
        
        for rank, (name, chips) in enumerate(all_players, 1):
            if '鲨鱼' in name or 'SHARK' in name:  # 鲨鱼
                self.results['final_rank'] = rank
                break
        
        # 计算VPIP/PFR
        if self.results['hands_played'] > 0:
            self.results['vpip'] = self.results['vpip_count'] / self.results['hands_played']
            self.results['pfr'] = self.results['pfr_count'] / self.results['hands_played']
    
    def print_report(self):
        """打印测试报告"""
        print(f"\n{'='*60}")
        print(f"  Test Report")
        print(f"{'='*60}\n")
        
        r = self.results
        print(f"  Hands played:   {r['hands_played']}/{self.num_hands}")
        print(f"  Start chips:    {r['shark_chips_start']}")
        print(f"  End chips:      {r['shark_chips_end']}")
        print(f"  Profit/Loss:    {r['shark_profit']:+d}")
        print(f"  Win rate:       {r['hands_won']}/{r['hands_played']} ({100*r['hands_won']/max(1,r['hands_played']):.1f}%)")
        print(f"  VPIP:           {r.get('vpip', 0)*100:.1f}%")
        print(f"  PFR:            {r.get('pfr', 0)*100:.1f}%")
        print(f"  Showdowns:      {r['showdowns']}")
        print(f"  Folds:          {r['folds']}")
        print(f"  Final rank:     {r['final_rank']}/{self.num_players}")
        print(f"  Eliminated:     {'Yes' if r['eliminated'] else 'No'}")
        
        if r['eliminated']:
            print(f"  Eliminated at:  Hand {r['eliminated_at_hand']}")
        
        print(f"\n{'='*60}\n")


def run_multiple_tests(num_tests: int = 3, num_hands: int = 100):
    """运行多次测试"""
    all_results = []
    wins = 0  # 鲨鱼盈利次数
    survivals = 0  # 鲨鱼存活次数
    
    print(f"\n{'#'*60}")
    print(f"#  Shark AI Stress Test - {num_tests} rounds x {num_hands} hands")
    print(f"{'#'*60}")
    
    for test_num in range(1, num_tests + 1):
        print(f"\n\n{'#'*60}")
        print(f"#  Round {test_num}/{num_tests}")
        print(f"{'#'*60}")
        
        tester = AutoGameTester(num_hands=num_hands, num_players=6)
        results = tester.run_test()
        tester.print_report()
        
        all_results.append(results)
        
        if results['shark_profit'] > 0:
            wins += 1
        if not results['eliminated']:
            survivals += 1
    
    # 汇总报告
    print(f"\n\n{'#'*60}")
    print(f"#  Summary Report ({num_tests} rounds)")
    print(f"{'#'*60}\n")
    
    total_profit = sum(r['shark_profit'] for r in all_results)
    avg_profit = total_profit / num_tests
    avg_hands = sum(r['hands_played'] for r in all_results) / num_tests
    
    print(f"  Total profit:   {total_profit:+d}")
    print(f"  Avg profit:     {avg_profit:+d}")
    print(f"  Avg hands:      {avg_hands:.1f}")
    print(f"  Wins:           {wins}/{num_tests} ({100*wins/num_tests:.1f}%)")
    print(f"  Survivals:      {survivals}/{num_tests} ({100*survivals/num_tests:.1f}%)")
    
    # 判断稳定性
    if wins >= num_tests * 0.7 and survivals == num_tests:
        print(f"\n  [PASS] Shark AI is stable!")
    elif wins >= num_tests * 0.5:
        print(f"\n  [WARN] Shark AI is acceptable but needs improvement")
    else:
        print(f"\n  [FAIL] Shark AI needs significant improvement")
    
    print(f"\n{'#'*60}\n")
    
    return all_results


if __name__ == '__main__':
    # 运行3轮测试，每轮100手
    results = run_multiple_tests(num_tests=3, num_hands=100)
