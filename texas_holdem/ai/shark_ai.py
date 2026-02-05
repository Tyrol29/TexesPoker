"""
鲨鱼AI - 自适应学习对手风格的AI
包含：位置感知、精确赔率计算、SPR策略、听牌评估
"""

import random
from typing import Dict, List, Tuple, Any, Optional
from texas_holdem.core.player import Player
from texas_holdem.game.betting import BettingRound
from texas_holdem.utils.constants import GameState
from texas_holdem.core.card import Card


class DrawEvaluator:
    """听牌评估器"""
    
    @staticmethod
    def identify_draws(hole_cards: List[Card], community_cards: List[Card]) -> Dict[str, Any]:
        """识别所有可能的听牌"""
        draws = {}
        if not community_cards:
            return draws
        
        all_cards = hole_cards + community_cards
        values = sorted(set([c.value for c in all_cards]))
        suits = [c.suit for c in all_cards]
        
        # 同花听牌检测
        for suit in set(suits):
            suited_cards = [c for c in all_cards if c.suit == suit]
            if len(suited_cards) == 4:
                # 检查是否是后门同花（只有2张同花色）
                hole_suited = [c for c in hole_cards if c.suit == suit]
                if len(hole_suited) >= 1:
                    draws['flush_draw'] = {'outs': 9, 'equity': 0.35}
        
        # 检查后门同花
        for suit in set(suits):
            suited_count = suits.count(suit)
            if suited_count == 3 and len(community_cards) == 3:
                draws['backdoor_flush'] = {'outs': 1, 'equity': 0.04}
        
        # 顺子听牌检测
        if len(values) >= 4:
            # 检查两端顺子听牌 (OESD)
            for i in range(len(values) - 3):
                if values[i+3] - values[i] == 3 and len(set(values[i:i+4])) == 4:
                    draws['oesd'] = {'outs': 8, 'equity': 0.31}
                    break
            
            # 检查卡顺听牌 (Gutshot)
            for i in range(len(values) - 3):
                gap = values[i+3] - values[i]
                if gap == 4 and len(set(values[i:i+4])) == 4:
                    draws['gutshot'] = {'outs': 4, 'equity': 0.16}
                    break
        
        # 检查高牌 Outs
        hole_values = sorted([c.value for c in hole_cards], reverse=True)
        if hole_values[0] >= 12:  # A或K
            overcard_outs = sum(1 for v in hole_values if v > max(community_cards, key=lambda x: x.value).value)
            if overcard_outs > 0:
                draws['overcards'] = {'outs': overcard_outs * 3, 'equity': overcard_outs * 0.12}
        
        # 组合听牌
        if 'flush_draw' in draws and 'oesd' in draws:
            draws['combo_draw'] = {'outs': 15, 'equity': 0.54}
        elif 'flush_draw' in draws and 'gutshot' in draws:
            draws['combo_draw'] = {'outs': 12, 'equity': 0.45}
        
        return draws
    
    @staticmethod
    def calculate_total_equity(draws: Dict) -> float:
        """计算听牌总胜率"""
        if not draws:
            return 0.0
        # 取最大equity，避免重复计算
        return max(d['equity'] for d in draws.values())


class PositionAwareness:
    """位置感知系统"""
    
    # 位置价值乘数（影响入池阈值）
    POSITION_MULTIPLIERS = {
        'EP': 0.70,    # 早位：收紧
        'MP': 0.85,    # 中位：标准
        'CO': 1.10,    # Cutoff：抢盲位置，放宽
        'BTN': 1.25,   # 按钮位：最大优势，大幅放宽
        'SB': 0.90,    # 小盲：位置劣势但可能有价格
        'BB': 1.00,    # 大盲：最后行动，有价格优势
    }
    
    @classmethod
    def get_position(cls, player: Player, total_players: int = 6) -> str:
        """确定玩家位置"""
        if player.is_dealer:
            return 'BTN'
        elif player.is_small_blind:
            return 'SB'
        elif player.is_big_blind:
            return 'BB'
        else:
            # 根据与庄家的距离判断
            # 简化处理：6人桌时，BTN前两个是CO和MP，再往前是EP
            return 'MP'  # 简化处理
    
    @classmethod
    def get_adjusted_threshold(cls, base_threshold: float, position: str) -> float:
        """根据位置调整入池阈值"""
        multiplier = cls.POSITION_MULTIPLIERS.get(position, 1.0)
        return base_threshold * multiplier


class PotOddsCalculator:
    """底池赔率计算器（包含隐含赔率）"""
    
    @staticmethod
    def calculate_direct_odds(amount_to_call: int, total_pot: int) -> float:
        """计算直接赔率"""
        if amount_to_call <= 0:
            return 0.0
        return amount_to_call / (total_pot + amount_to_call)
    
    @staticmethod
    def calculate_implied_odds(amount_to_call: int, total_pot: int, 
                               effective_stack: int, street: str,
                               draw_equity: float) -> Dict[str, float]:
        """计算隐含赔率
        
        Args:
            amount_to_call: 需要跟注的金额
            total_pot: 当前底池
            effective_stack: 有效筹码（最小筹码量）
            street: 'flop', 'turn', 'river'
            draw_equity: 听牌胜率
        """
        if amount_to_call <= 0:
            return {'total_equity': 0.0, 'should_call': True}
        
        # 街数乘数（后续还能赢多少）
        street_multiplier = {'flop': 2.5, 'turn': 1.3, 'river': 1.0}
        multiplier = street_multiplier.get(street, 1.0)
        
        # 估算后续能赢的平均金额（基于听牌强度和剩余筹码）
        potential_future_win = min(effective_stack * 0.3 * draw_equity * multiplier, 
                                   effective_stack * 0.5)
        
        # 总底池 = 当前底池 + 未来可能赢的
        total_potential = total_pot + potential_future_win
        
        # 直接胜率需求
        direct_equity_needed = amount_to_call / (total_pot + amount_to_call)
        
        # 考虑隐含赔率后的实际胜率需求
        if total_potential > amount_to_call:
            implied_equity_needed = amount_to_call / total_potential
        else:
            implied_equity_needed = direct_equity_needed
        
        return {
            'direct_equity_needed': direct_equity_needed,
            'implied_equity_needed': implied_equity_needed,
            'potential_future_win': potential_future_win,
            'should_call': draw_equity > implied_equity_needed * 0.9  # 稍微放宽
        }


class SPRStrategy:
    """SPR（筹码底池比）策略"""
    
    @staticmethod
    def calculate_spr(effective_stack: int, pot: int) -> float:
        """计算SPR值"""
        if pot <= 0:
            return float('inf')
        return effective_stack / pot
    
    @classmethod
    def get_strategy_by_spr(cls, spr: float, hand_strength: float, 
                           draw_equity: float = 0) -> Dict[str, Any]:
        """根据SPR和手牌强度获取策略"""
        
        total_equity = hand_strength * 0.7 + draw_equity * 0.3
        
        if spr > 15:
            # 深筹码：玩隐含赔率，投机牌有价值
            return {
                'play_speculative': True,
                'set_mine': True,
                'commit_threshold': 0.75,
                'avoid_light_commit': True,
                'hand_requirement': 0.55
            }
        elif spr > 7:
            # 中等筹码：平衡策略
            return {
                'play_speculative': draw_equity > 0.25,
                'set_mine': True,
                'commit_threshold': 0.65,
                'avoid_light_commit': False,
                'hand_requirement': 0.50
            }
        elif spr > 3:
            # 短筹码：追求全押，不玩投机牌
            return {
                'play_speculative': False,
                'set_mine': False,
                'commit_threshold': 0.55,
                'avoid_light_commit': False,
                'hand_requirement': 0.48,
                'push_fold': False
            }
        else:
            # 超短筹码：全押或弃牌
            return {
                'play_speculative': False,
                'set_mine': False,
                'commit_threshold': 0.45,
                'avoid_light_commit': False,
                'hand_requirement': 0.42,
                'push_fold': True  # 全押或弃牌模式
            }


class SharkAI:
    """
    鲨鱼AI - 自适应学习AI v2.0
    
    核心改进：
    1. 位置感知系统 - 根据位置调整范围
    2. 精确赔率计算 - 直接赔率+隐含赔率
    3. SPR策略 - 根据筹码深度调整
    4. 听牌评估 - 精确识别和评估听牌
    5. 对手学习 - 20手后自适应调整
    """
    
    # Sklansky前4组强牌门槛 (约前16%的手牌，牌力 >= 0.60)
    # 前4组包含：AA-88, AKs-A9s, AKo-AJo, KQs-KTs, KQo, QJs-Q9s, QJo, JTs, J9s, T9s
    TIER3_THRESHOLD = 0.60
    
    def __init__(self):
        # 初始使用紧凶(TAG)风格，只玩前3组强牌，学习后动态调整
        self.base_config = {
            'vpip_range': (12, 18),      # TAG - 紧：只玩好牌
            'pfr_range': (10, 16),       # TAG - 凶：多数时候加注而非跟注
            'af_factor': 2.5,            # 高攻击性
            'bluff_freq': 0.15,          # 适度诈唬
            'call_preflop': 0.20,        # 少跟注
            'raise_preflop': 0.25,       # 多加注
            'bet_postflop': 0.45,        # 翻牌后积极下注
            'fold_to_raise': 0.60,       # 面对加注容易弃牌（尊重对手）
            'adaptation_start': 20,
            'learning_rate': 0.1,
        }
        
        # 对手追踪数据
        self.opponent_data: Dict[str, Dict] = {}
        self.adaptation_active = False
        self.hands_observed = 0
        self.current_config = self.base_config.copy()
        
        # 子系统
        self.draw_evaluator = DrawEvaluator()
        self.position_awareness = PositionAwareness()
        self.pot_odds_calc = PotOddsCalculator()
        self.spr_strategy = SPRStrategy()
        
        # 游戏状态追踪
        self.current_street = 'preflop'
        self.total_pot = 0
        self.effective_stack = 0
    
    def initialize_opponents(self, players: List[Player]):
        """初始化对手追踪"""
        self.opponent_data = {}
        for player in players:
            if not player.is_ai or getattr(player, 'ai_style', 'LAG') != 'SHARK':
                self.opponent_data[player.name] = {
                    'hands_observed': 0,
                    'folds': 0,
                    'calls': 0,
                    'raises': 0,
                    'bluffs_detected': 0,
                    'bluff_opportunities': 0,
                    'fold_to_cbet': 0,
                    'cbet_opportunities': 0,
                    'showdown_wins': 0,
                    'showdowns': 0,
                    'fold_tendency': 0.5,
                    'bluff_tendency': 0.5,
                    'calling_tendency': 0.5,
                }
        self.adaptation_active = False
        self.hands_observed = 0
        self.current_config = self.base_config.copy()
    
    def update_after_action(self, player_name: str, action: str, street: str,
                           is_bluff: bool = False, facing_cbet: bool = False):
        """每轮行动后更新对手数据"""
        if player_name not in self.opponent_data:
            return
        
        data = self.opponent_data[player_name]
        data['hands_observed'] += 1
        self.hands_observed += 1
        
        if action == 'fold':
            data['folds'] += 1
            if facing_cbet:
                data['fold_to_cbet'] += 1
        elif action in ['call']:
            data['calls'] += 1
        elif action in ['raise', 'bet']:
            data['raises'] += 1
            if is_bluff:
                data['bluffs_detected'] += 1
        
        if facing_cbet:
            data['cbet_opportunities'] += 1
        
        if not self.adaptation_active:
            total_hands = sum(d['hands_observed'] for d in self.opponent_data.values())
            if total_hands >= self.base_config['adaptation_start']:
                self.adaptation_active = True
        
        if data['hands_observed'] % 5 == 0 or self.adaptation_active:
            self._calculate_tendencies(player_name)
            if self.adaptation_active:
                self._update_strategy()
    
    def _calculate_tendencies(self, player_name: str):
        """计算对手的倾向值"""
        data = self.opponent_data[player_name]
        hands = data['hands_observed']
        
        if hands < 3:
            return
        
        fold_rate = data['folds'] / hands
        data['fold_tendency'] = min(1.0, max(0.0, fold_rate * 2))
        
        if data['raises'] > 0:
            bluff_rate = data['bluffs_detected'] / data['raises']
            data['bluff_tendency'] = min(1.0, bluff_rate * 3)
        
        if hands > data['folds']:
            calling_rate = data['calls'] / (hands - data['folds'])
            data['calling_tendency'] = min(1.0, max(0.0, calling_rate))
    
    def _update_strategy(self):
        """根据对手数据更新当前策略配置"""
        if not self.opponent_data:
            return
        
        avg_fold = sum(d['fold_tendency'] for d in self.opponent_data.values()) / len(self.opponent_data)
        avg_bluff = sum(d['bluff_tendency'] for d in self.opponent_data.values()) / len(self.opponent_data)
        avg_call = sum(d['calling_tendency'] for d in self.opponent_data.values()) / len(self.opponent_data)
        
        adjustments = []
        
        # 对手容易弃牌 -> 增加诈唬
        if avg_fold > 0.6:
            self.current_config['bluff_freq'] = min(0.5, self.base_config['bluff_freq'] + 0.15)
            self.current_config['bet_postflop'] = min(0.7, self.base_config['bet_postflop'] + 0.15)
            self.current_config['af_factor'] = self.base_config['af_factor'] + 0.5
            adjustments.append("对手易弃牌→增加诈唬")
        
        # 对手喜欢诈唬 -> 打得更紧
        if avg_bluff > 0.4:
            self.current_config['vpip_range'] = (
                max(15, self.base_config['vpip_range'][0] - 5),
                max(20, self.base_config['vpip_range'][1] - 5)
            )
            self.current_config['call_preflop'] = min(0.4, self.base_config['call_preflop'] + 0.1)
            self.current_config['fold_to_raise'] = max(0.3, self.base_config['fold_to_raise'] - 0.1)
            adjustments.append("对手爱诈唬→收紧范围")
        
        # 对手跟注站 -> 减少诈唬，增加价值下注
        if avg_call > 0.5:
            self.current_config['bluff_freq'] = max(0.1, self.base_config['bluff_freq'] - 0.1)
            self.current_config['bet_postflop'] = self.base_config['bet_postflop'] + 0.1
            self.current_config['af_factor'] = self.base_config['af_factor'] + 0.3
            adjustments.append("对手跟注多→减少诈唬")
        
        if not adjustments:
            self.current_config = self.base_config.copy()
    
    def get_action(self, player: Player, betting_round: BettingRound,
                   hand_strength: float, win_probability: float,
                   pot_odds: float, ev: float) -> Tuple[Any, int]:
        """鲨鱼AI主决策方法"""
        from texas_holdem.utils.constants import Action
        
        game_state = betting_round.game_state
        available_actions = betting_round.get_available_actions(player)
        amount_to_call = betting_round.get_amount_to_call(player)
        current_bet = game_state.current_bet if hasattr(game_state, 'current_bet') else 0
        # 底池在 table.total_pot 中
        if hasattr(game_state, 'table') and hasattr(game_state.table, 'total_pot'):
            total_pot = game_state.table.total_pot
        else:
            total_pot = 0
        
        # 获取位置信息
        position = self.position_awareness.get_position(player)
        
        # 计算SPR和有效筹码
        players = game_state.players if hasattr(game_state, 'players') else []
        active_players = [p for p in players if p.is_active]
        self.effective_stack = min(player.chips, 
                                   sum(p.chips for p in active_players) / 
                                   max(1, len(active_players) - 1))
        spr = self.spr_strategy.calculate_spr(self.effective_stack, total_pot)
        
        # 识别听牌
        hole_cards = player.hand.cards if player.hand else []
        community_cards = game_state.table.community_cards if hasattr(game_state, 'table') else []
        draws = self.draw_evaluator.identify_draws(hole_cards, community_cards)
        draw_equity = self.draw_evaluator.calculate_total_equity(draws)
        
        # 确定当前街
        street_map = {
            GameState.PRE_FLOP: 'preflop',
            GameState.FLOP: 'flop',
            GameState.TURN: 'turn',
            GameState.RIVER: 'river',
            GameState.SHOWDOWN: 'river'
        }
        self.current_street = street_map.get(game_state.state, 'preflop')
        
        config = self.current_config
        is_preflop = (game_state.state == GameState.PRE_FLOP)
        
        # 计算综合胜率（手牌+听牌）
        total_equity = win_probability + draw_equity * 0.5
        
        # 计算精确赔率
        direct_odds = self.pot_odds_calc.calculate_direct_odds(amount_to_call, total_pot)
        implied_calc = self.pot_odds_calc.calculate_implied_odds(
            amount_to_call, total_pot, self.effective_stack, 
            self.current_street, draw_equity
        )
        
        # SPR策略指导
        spr_guidance = self.spr_strategy.get_strategy_by_spr(spr, hand_strength, draw_equity)
        
        # 翻牌前决策
        if is_preflop:
            return self._preflop_decision(
                player, available_actions, amount_to_call, 
                hand_strength, position, spr_guidance, config
            )
        
        # 翻牌后决策
        return self._postflop_decision(
            player, available_actions, amount_to_call, current_bet,
            hand_strength, draw_equity, total_equity, direct_odds, 
            implied_calc, spr_guidance, config, draws, total_pot
        )
    
    def _preflop_decision(self, player, available_actions, amount_to_call,
                         hand_strength, position, spr_guidance, config) -> Tuple[Any, int]:
        """翻牌前决策 - TAG风格，只玩Sklansky前3组强牌"""
        from texas_holdem.utils.constants import Action
        
        available_names = [str(a).lower().replace('action.', '') for a in available_actions]
        
        # TAG风格：玩Sklansky前4组强牌 (牌力 >= 0.60)，约16%的手牌
        # 第1-2组(0.80+): AA-QQ, AKs, AKo - 大加注
        # 第3组(0.70-0.80): JJ-TT, AQs-AJs, KQs, AQo - 标准加注/跟注
        # 第4组(0.60-0.70): 99-88, ATs-A9s, KJs-KTs, QJs, JTs - 后位加注，早位弃牌
        tier_threshold = self.TIER3_THRESHOLD
        
        # 位置调整（后位放宽）
        position_multipliers = {'EP': 1.0, 'MP': 0.98, 'CO': 0.95, 'BTN': 0.93, 'SB': 0.98, 'BB': 0.95}
        adjusted_threshold = tier_threshold * position_multipliers.get(position, 1.0)
        
        # 牌力不够直接弃牌（除非大盲可以check）
        if hand_strength < adjusted_threshold:
            if amount_to_call <= 0 and 'check' in available_names:
                return Action.CHECK, 0
            return Action.FOLD, 0
        
        # 强牌分组决策
        if hand_strength >= 0.80:  # 第1-2组超强牌 (AA-QQ, AKs, AKo)
            if 'raise' in available_names:
                # TAG风格：大加注施压
                raise_amount = max(40, amount_to_call + 30)
                return Action.RAISE, raise_amount
            elif 'bet' in available_names:
                return Action.BET, 40
        
        elif hand_strength >= 0.70:  # 第3组强牌 (JJ-TT, AQs等)
            if position in ['EP', 'MP']:
                # 早位：跟注看翻牌
                if amount_to_call > 0 and 'call' in available_names:
                    return Action.CALL, 0
                elif 'check' in available_names:
                    return Action.CHECK, 0
                elif 'raise' in available_names:
                    return Action.RAISE, 40
            else:
                # 后位：加注偷盲
                if 'raise' in available_names:
                    return Action.RAISE, 40
                elif 'call' in available_names:
                    return Action.CALL, 0
        
        else:  # 第4组中等牌 (0.60-0.70: 99-88, ATs, KJs等)
            if position in ['CO', 'BTN', 'SB']:  # 只在后位玩
                if 'raise' in available_names and amount_to_call <= 20:
                    return Action.RAISE, 40  # 偷盲
                elif 'call' in available_names and amount_to_call <= 20:
                    return Action.CALL, 0
            # 早位弃牌这些牌
            if amount_to_call <= 0 and 'check' in available_names:
                return Action.CHECK, 0
            return Action.FOLD, 0
        
        # 默认弃牌
        return Action.FOLD, 0
    
    def _postflop_decision(self, player, available_actions, amount_to_call,
                          current_bet, hand_strength, draw_equity, total_equity,
                          direct_odds, implied_calc, spr_guidance, config, draws, total_pot) -> Tuple[Any, int]:
        """翻牌后决策"""
        from texas_holdem.utils.constants import Action
        
        available_names = [str(a).lower().replace('action.', '') for a in available_actions]
        
        # 超短筹码全押或弃牌模式
        if spr_guidance.get('push_fold', False):
            if total_equity >= spr_guidance['commit_threshold']:
                return Action.ALL_IN, player.chips
            else:
                return Action.FOLD, 0
        
        # 有听牌时的决策
        if draw_equity > 0.15:
            # 检查赔率是否足够
            if implied_calc['should_call'] and 'call' in available_names:
                return Action.CALL, 0
            # 强听牌可以半诈唬加注
            if draw_equity > 0.30 and 'raise' in available_names and hand_strength < 0.5:
                return Action.RAISE, max(40, current_bet + 20)
        
        # 基于手牌强度的权重计算
        action_weights = self._calculate_postflop_weights(
            hand_strength, draw_equity, config, spr_guidance
        )
        
        # 过滤可用行动
        valid = {k: v for k, v in action_weights.items() if k in available_names and v > 0}
        
        # 如果可以check，避免fold
        if 'check' in available_names and 'fold' in valid:
            del valid['fold']
        
        if not valid:
            return Action.FOLD, 0
        
        # 加权选择
        action_name = self._weighted_choice(valid)
        
        action_map = {
            'fold': Action.FOLD,
            'check': Action.CHECK,
            'call': Action.CALL,
            'bet': Action.BET,
            'raise': Action.RAISE,
            'all_in': Action.ALL_IN
        }
        action = action_map.get(action_name, Action.FOLD)
        
        # 计算金额
        amount = self._calculate_amount(
            action, player, amount_to_call, current_bet, 
            hand_strength, draw_equity, config, total_pot
        )
        
        return action, amount
    
    def _calculate_postflop_weights(self, hand_strength: float, draw_equity: float,
                                    config: Dict, spr_guidance: Dict) -> Dict[str, float]:
        """计算翻牌后行动权重"""
        weights = {'fold': 0, 'check': 0, 'call': 0, 'bet': 0, 'raise': 0, 'all_in': 0}
        
        total_equity = hand_strength * 0.7 + draw_equity * 0.3
        bluff_freq = config['bluff_freq']
        af = config['af_factor']
        
        if total_equity > 0.80:  # 坚果或接近坚果
            weights.update({
                'raise': 0.50,
                'bet': 0.35,
                'call': 0.15
            })
        elif total_equity > 0.60:  # 强牌
            weights.update({
                'bet': 0.45,
                'raise': 0.25,
                'call': 0.25,
                'check': 0.05
            })
        elif total_equity > 0.45:  # 中等牌
            weights.update({
                'call': 0.45,
                'check': 0.30,
                'bet': 0.15,
                'fold': 0.10
            })
        elif total_equity > 0.30 or draw_equity > 0.15:  # 弱牌+听牌
            weights.update({
                'call': 0.35,
                'check': 0.30,
                'fold': 0.25,
                'bet': 0.08 * bluff_freq * 10
            })
        else:  # 纯弱牌
            weights.update({
                'fold': 0.55,
                'check': 0.35,
                'call': 0.08,
                'bet': 0.02 * bluff_freq * 10
            })
        
        return weights
    
    def _calculate_amount(self, action, player, amount_to_call, current_bet,
                         hand_strength, draw_equity, config, total_pot: int = 0) -> int:
        """计算下注金额 - 基于底池百分比"""
        if action in ['fold', 'check', 'call']:
            return 0
        elif action == 'all_in':
            return player.chips
        
        # 确保有底池信息，如果没有则使用默认值
        if total_pot <= 0:
            total_pot = 100  # 默认底池
        
        big_blind = 20
        af = config['af_factor']
        total_strength = hand_strength + draw_equity * 0.5
        
        # 基于底池百分比计算下注额（标准扑克下注尺度）
        if current_bet == 0:  # bet (没人下注时)
            if total_strength > 0.80:  # 坚果/超强牌 - 大注索取价值
                bet_size = int(total_pot * 0.75)
            elif total_strength > 0.60:  # 强牌 - 标准价值下注
                bet_size = int(total_pot * 0.66)
            elif draw_equity > 0.25:  # 强听牌 - 半诈唬，大注施压
                bet_size = int(total_pot * 0.60)
            elif total_strength > 0.45:  # 中等牌 - 小注控池
                bet_size = int(total_pot * 0.33)
            else:  # 弱牌/诈唬 - 小注或标准注
                bet_size = int(total_pot * 0.25)
            
            # 确保至少是大盲的2倍
            return max(big_blind * 2, bet_size)
            
        else:  # raise (有人已下注时)
            # 计算加注额（基于当前下注额的增长）
            min_raise = max(big_blind * 2, current_bet)
            
            if total_strength > 0.80:  # 超强牌 - 大加注
                raise_size = int(current_bet + total_pot * 0.75)
            elif total_strength > 0.60:  # 强牌 - 标准加注
                raise_size = int(current_bet + total_pot * 0.50)
            elif draw_equity > 0.25:  # 听牌 - 半诈唬加注
                raise_size = int(current_bet + total_pot * 0.40)
            else:  # 弱牌 - 最小加注
                raise_size = min_raise
            
            return max(min_raise, raise_size)
    
    def _weighted_choice(self, weights: Dict[str, float]) -> str:
        """加权随机选择"""
        total = sum(weights.values())
        if total == 0:
            return 'fold'
        
        r = random.random() * total
        cumulative = 0
        for action, weight in weights.items():
            cumulative += weight
            if r <= cumulative:
                return action
        return list(weights.keys())[-1]
    
    def get_opponent_summary(self) -> str:
        """获取对手分析摘要"""
        if not self.adaptation_active:
            return "[🦈 鲨鱼AI] 观察中..."
        
        summaries = []
        for name, data in self.opponent_data.items():
            if data['hands_observed'] >= 5:
                fold_desc = "易弃牌" if data['fold_tendency'] > 0.6 else \
                           "难弃牌" if data['fold_tendency'] < 0.4 else "中等"
                bluff_desc = "爱诈唬" if data['bluff_tendency'] > 0.4 else \
                            "诚实" if data['bluff_tendency'] < 0.2 else "平衡"
                summaries.append(f"{name}({fold_desc}/{bluff_desc})")
        
        if summaries:
            return f"[🦈 鲨鱼AI] 分析: {', '.join(summaries)}"
        return "[🦈 鲨鱼AI] 学习中..."
