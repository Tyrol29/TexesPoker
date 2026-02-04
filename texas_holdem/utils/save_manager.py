"""
游戏存档管理器
负责保存和加载游戏状态
"""

import json
import os
import pickle
from typing import Dict, Any, Optional
from datetime import datetime


class SaveManager:
    """游戏存档管理器"""
    
    SAVE_DIR = "saves"
    
    @classmethod
    def ensure_save_dir(cls):
        """确保存档目录存在"""
        if not os.path.exists(cls.SAVE_DIR):
            os.makedirs(cls.SAVE_DIR)
    
    @classmethod
    def save_game(cls, save_data: Dict[str, Any], slot: int = 1) -> bool:
        """
        保存游戏状态
        
        Args:
            save_data: 要保存的游戏数据字典
            slot: 存档槽位（1-3）
        
        Returns:
            是否保存成功
        """
        try:
            cls.ensure_save_dir()
            
            filename = f"save_{slot}.json"
            filepath = os.path.join(cls.SAVE_DIR, filename)
            
            # 添加保存时间戳
            save_data['save_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"保存游戏失败: {e}")
            return False
    
    @classmethod
    def load_game(cls, slot: int = 1) -> Optional[Dict[str, Any]]:
        """
        加载游戏状态
        
        Args:
            slot: 存档槽位（1-3）
        
        Returns:
            游戏数据字典，如果存档不存在则返回 None
        """
        try:
            filename = f"save_{slot}.json"
            filepath = os.path.join(cls.SAVE_DIR, filename)
            
            if not os.path.exists(filepath):
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载游戏失败: {e}")
            return None
    
    @classmethod
    def has_save(cls, slot: int = 1) -> bool:
        """检查指定槽位是否有存档"""
        filename = f"save_{slot}.json"
        filepath = os.path.join(cls.SAVE_DIR, filename)
        return os.path.exists(filepath)
    
    @classmethod
    def get_save_info(cls, slot: int = 1) -> Optional[str]:
        """获取存档信息（时间戳）"""
        data = cls.load_game(slot)
        if data:
            return data.get('save_time', '未知时间')
        return None
    
    @classmethod
    def list_saves(cls) -> Dict[int, str]:
        """列出所有存档"""
        saves = {}
        for slot in range(1, 4):
            if cls.has_save(slot):
                info = cls.get_save_info(slot)
                saves[slot] = info
        return saves
    
    @classmethod
    def delete_save(cls, slot: int = 1) -> bool:
        """删除指定存档"""
        try:
            filename = f"save_{slot}.json"
            filepath = os.path.join(cls.SAVE_DIR, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
            return False
        except Exception:
            return False


class GameStateEncoder:
    """游戏状态编码器 - 将游戏对象转换为可序列化的字典"""
    
    @staticmethod
    def encode_card(card) -> Dict[str, Any]:
        """编码扑克牌"""
        if card is None:
            return None
        return {
            'suit': card.suit,
            'rank': card.rank,
            'value': card.value
        }
    
    @staticmethod
    def encode_hand(hand) -> list:
        """编码手牌"""
        return [GameStateEncoder.encode_card(card) for card in hand.get_cards()]
    
    @staticmethod
    def encode_player(player) -> Dict[str, Any]:
        """编码玩家"""
        return {
            'name': player.name,
            'chips': player.chips,
            'is_ai': player.is_ai,
            'ai_style': getattr(player, 'ai_style', None),
            'hand': GameStateEncoder.encode_hand(player.hand),
            'bet_amount': player.bet_amount,
            'is_active': player.is_active,
            'is_all_in': player.is_all_in,
            'has_acted': player.has_acted,
            'is_dealer': player.is_dealer,
            'is_small_blind': player.is_small_blind,
            'is_big_blind': player.is_big_blind
        }
    
    @staticmethod
    def encode_table(table) -> Dict[str, Any]:
        """编码牌桌"""
        return {
            'community_cards': [GameStateEncoder.encode_card(c) for c in table.get_community_cards()],
            'total_pot': table.total_pot,
            'side_pots': table.side_pots
        }
    
    @staticmethod
    def encode_game_state(game_state) -> Dict[str, Any]:
        """编码游戏状态"""
        return {
            'state': game_state.state,
            'current_player_index': game_state.current_player_index,
            'current_bet': game_state.current_bet,
            'last_raiser_index': game_state.last_raiser_index,
            'min_raise': game_state.min_raise,
            'hand_number': game_state.hand_number,
            'table': GameStateEncoder.encode_table(game_state.table)
        }
    
    @staticmethod
    def encode_game_engine(engine, is_mid_hand: bool = False) -> Dict[str, Any]:
        """
        编码游戏引擎
        
        Args:
            engine: 游戏引擎实例
            is_mid_hand: 是否在手牌进行中（需要保存当前手牌状态）
        """
        return {
            'players': [GameStateEncoder.encode_player(p) for p in engine.players],
            'game_state': GameStateEncoder.encode_game_state(engine.game_state),
            'is_mid_hand': is_mid_hand
        }


class GameStateDecoder:
    """游戏状态解码器 - 将字典还原为游戏对象"""
    
    @staticmethod
    def decode_card(data: Dict[str, Any]):
        """解码扑克牌"""
        if data is None:
            return None
        from ..core.card import Card
        return Card(data['suit'], data['rank'])
    
    @staticmethod
    def decode_hand(data: list):
        """解码手牌"""
        from ..core.hand import Hand
        hand = Hand()
        for card_data in data:
            card = GameStateDecoder.decode_card(card_data)
            if card:
                hand.add_card(card)
        return hand
    
    @staticmethod
    def decode_player(data: Dict[str, Any]):
        """解码玩家"""
        from ..core.player import Player
        player = Player(data['name'], data['chips'], data['is_ai'])
        player.ai_style = data.get('ai_style')
        player.hand = GameStateDecoder.decode_hand(data.get('hand', []))
        player.bet_amount = data.get('bet_amount', 0)
        player.is_active = data.get('is_active', True)
        player.is_all_in = data.get('is_all_in', False)
        player.has_acted = data.get('has_acted', False)
        player.is_dealer = data.get('is_dealer', False)
        player.is_small_blind = data.get('is_small_blind', False)
        player.is_big_blind = data.get('is_big_blind', False)
        return player
    
    @staticmethod
    def decode_table(data: Dict[str, Any]):
        """解码牌桌"""
        from ..core.table import Table
        table = Table()
        table.community_cards = [GameStateDecoder.decode_card(c) for c in data.get('community_cards', [])]
        table.total_pot = data.get('total_pot', 0)
        table.side_pots = data.get('side_pots', [])
        return table
    
    @staticmethod
    def decode_game_state(data: Dict[str, Any], players: list):
        """解码游戏状态"""
        from ..game.game_state import GameStateManager
        from ..utils.constants import GameState
        
        game_state = GameStateManager(players)
        game_state.state = data.get('state', GameState.PRE_FLOP)
        game_state.current_player_index = data.get('current_player_index', 0)
        game_state.current_bet = data.get('current_bet', 0)
        game_state.last_raiser_index = data.get('last_raiser_index', -1)
        game_state.min_raise = data.get('min_raise', 0)
        game_state.hand_number = data.get('hand_number', 0)
        game_state.table = GameStateDecoder.decode_table(data.get('table', {}))
        game_state.active_players = [p for p in players if p.is_active]
        return game_state
