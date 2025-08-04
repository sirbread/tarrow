import sys
import json
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QSlider, QCheckBox, QComboBox,
                            QListWidget, QTabWidget, QColorDialog, QSpinBox,
                            QSystemTrayIcon, QMenu, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QThread, QPoint, QObject, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QIcon, QPixmap, QCursor, QPainterPath

import psutil
import platform
import time
from datetime import datetime
from functools import lru_cache
from collections import deque
from pynput import keyboard

class CatppuccinTheme:
    COLORS = {
        'base': '#1e1e2e',
        'mantle': '#181825', 
        'crust': '#11111b',
        'text': '#cdd6f4',
        'subtext1': '#bac2de',
        'subtext0': '#a6adc8',
        'overlay2': '#9399b2',
        'overlay1': '#7f849c',
        'overlay0': '#6c7086',
        'surface2': '#585b70',
        'surface1': '#45475a',
        'surface0': '#313244',
        'blue': '#89b4fa',
        'lavender': '#b4befe',
        'sapphire': '#74c7ec',
        'sky': '#89dceb',
        'teal': '#94e2d5',
        'green': '#a6e3a1',
        'yellow': '#f9e2af',
        'peach': '#fab387',
        'maroon': '#eba0ac',
        'red': '#f38ba8',
        'mauve': '#cba6f7',
        'pink': '#f5c2e7',
        'flamingo': '#f2cdcd',
        'rosewater': '#f5e0dc'
    }
    
    @classmethod
    @lru_cache(maxsize=32)  #opti :cache color lookups
    def get_color(cls, color_name):
        return cls.COLORS.get(color_name, '#ffffff')

class HotkeyListener(QThread):
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()
    hotkey_captured = pyqtSignal(str)

    def __init__(self, hotkey_name):
        super().__init__()
        self.hotkey_name = hotkey_name
        self.capturing = False
        self.listener = None
        self.key_down = False

    def get_key_str(self, key):
        try:
            return key.char
        except AttributeError:
            return key.name

    def on_press(self, key):
        key_str = self.get_key_str(key)
        if self.capturing:
            self.hotkey_captured.emit(key_str)
            self.capturing = False
            return

        if key_str == self.hotkey_name:
            if not self.key_down:
                self.key_down = True
                self.hotkey_pressed.emit()

    def on_release(self, key):
        if not self.capturing:
            key_str = self.get_key_str(key)
            if key_str == self.hotkey_name:
                self.key_down = False
                self.hotkey_released.emit()

    def run(self):
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()
        self.listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()

    def enter_capture_mode(self):
        self.capturing = True

class SystemStatsWorker(QThread):
    stats_updated = pyqtSignal(dict)
    first_load_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.update_interval = 2.0
        self.first_load = True
        
        self.last_process_check = 0
        self.process_cache = []
        self.process_check_interval = 5.0

        self.history_length = 60
        self.cpu_history = deque(maxlen=self.history_length)
        self.mem_history = deque(maxlen=self.history_length)
        self.disk_history = deque(maxlen=self.history_length)

        # For manual CPU calculation
        self.last_cpu_times = psutil.cpu_times()

    def run(self):
        while self.running:
            try:
                start_time = time.time()
                
                # Manual and more reliable CPU usage calculation
                t1 = self.last_cpu_times
                t2 = psutil.cpu_times()
                
                total_delta = sum(t2) - sum(t1)
                idle_delta = t2.idle - t1.idle
                
                if total_delta > 0:
                    cpu_percent = (1.0 - idle_delta / total_delta) * 100
                else:
                    cpu_percent = 0.0
                
                self.last_cpu_times = t2
                self.cpu_history.append(cpu_percent)
                
                mem_stats = self.get_memory_usage()
                self.mem_history.append(mem_stats['percent'])
                
                disk_stats = self.get_disk_usage()
                self.disk_history.append(disk_stats['percent'])

                net_stats = self.get_network_stats()
                
                top_cpu, top_memory = self.get_top_processes()
                
                cpu_temp = self.get_cpu_temperature()

                stats = {
                    'cpu': cpu_percent,
                    'cpu_temp': cpu_temp,
                    'memory': mem_stats,
                    'disk': disk_stats,
                    'network': net_stats,
                    'top_cpu': top_cpu,
                    'top_memory': top_memory,
                    'cpu_history': list(self.cpu_history),
                    'mem_history': list(self.mem_history),
                    'disk_history': list(self.disk_history)
                }
                
                self.stats_updated.emit(stats)
                
                if self.first_load:
                    self.first_load_complete.emit()
                    self.first_load = False
                    
                elapsed = time.time() - start_time
                sleep_time = max(0.1, self.update_interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Error collecting stats: {e}")
                time.sleep(self.update_interval)

    def get_cpu_temperature(self):
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if not temps:
                    return "N/A"
                
                # Look for common keys for CPU temperature
                for name in temps:
                    if 'core' in name.lower() or 'cpu' in name.lower() or 'k10' in name.lower() or 'zen' in name.lower():
                        if temps[name]:
                            return f"{temps[name][0].current:.0f}°C"
                
                # Fallback to the first available sensor if no common CPU key is found
                for name in temps:
                    if temps[name]:
                        return f"{temps[name][0].current:.0f}°C"

            return "N/A"
        except Exception as e:
            # This is not an error, it just means the platform is not supported
            return "N/A"

    def get_top_processes(self):
        current_time = time.time()
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                proc_info = proc.info
                name = proc_info.get('name', '')
                if not name or 'Idle' in name or name == 'System' or name == '[kernel_task]':
                    continue
                    
                processes.append({
                    'name': name[:25],
                    'cpu_percent': proc_info.get('cpu_percent', 0) or 0,
                    'memory_percent': proc_info.get('memory_percent', 0) or 0
                })
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        top_cpu = sorted([p for p in processes if p['cpu_percent'] > 0.1], key=lambda x: x['cpu_percent'], reverse=True)[:3]
        top_memory = sorted([p for p in processes if p['memory_percent'] > 0.1], key=lambda x: x['memory_percent'], reverse=True)[:3]
            
        return top_cpu, top_memory

    def get_memory_usage(self):
        mem = psutil.virtual_memory()
        return {
            'percent': mem.percent,
            'used': mem.used,
            'total': mem.total,
            'available': mem.available
        }
    
    def get_disk_usage(self):
        try:
            if os.name == 'nt':
                disk = psutil.disk_usage('C:/')
            else:
                disk = psutil.disk_usage('/')
            
            return {
                'percent': (disk.used / disk.total) * 100,
                'used': disk.used,
                'total': disk.total,
                'free': disk.free
            }
        except Exception as e:
            print(f"Error getting disk usage: {e}")
            return {'percent': 0, 'used': 0, 'total': 1, 'free': 1}
    
    def get_network_stats(self):
        try:
            net = psutil.net_io_counters()
            return {
                'bytes_sent': net.bytes_sent,
                'bytes_recv': net.bytes_recv,
                'packets_sent': net.packets_sent,
                'packets_recv': net.packets_recv
            }
        except Exception as e:
            print(f"Error getting network stats: {e}")
            return {'bytes_sent': 0, 'bytes_recv': 0, 'packets_sent': 0, 'packets_recv': 0}

    def set_update_interval(self, interval):
        self.update_interval = float(interval)
    
    def stop(self):
        self.running = False
        self.wait()

class DragPreview(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.edge = 'right'
        self.resize(30, 60)
        
    def set_edge_and_size(self, edge):
        self.edge = edge
        if edge in ['top', 'bottom']:
            self.resize(60, 30)
        else:
            self.resize(30, 60)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor(CatppuccinTheme.get_color('surface1'))
        bg_color.setAlpha(120)
        accent_color = QColor(CatppuccinTheme.get_color('blue'))
        accent_color.setAlpha(120)
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(accent_color, 2))
        painter.drawRoundedRect(self.rect(), 8, 8)
        
        painter.setBrush(QBrush(accent_color))
        painter.setPen(QPen(accent_color, 2))
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        if self.edge == 'right':
            points = [(center_x + 5, center_y - 8), (center_x - 5, center_y), (center_x + 5, center_y + 8)]
        elif self.edge == 'left':
            points = [(center_x - 5, center_y - 8), (center_x + 5, center_y), (center_x - 5, center_y + 8)]
        elif self.edge == 'top':
            points = [(center_x - 8, center_y - 5), (center_x, center_y + 5), (center_x + 8, center_y - 5)]
        else:
            points = [(center_x - 8, center_y + 5), (center_x, center_y - 5), (center_x + 8, center_y + 5)]
        
        from PyQt6.QtGui import QPolygon
        polygon = QPolygon([QPoint(x, y) for x, y in points])
        painter.drawPolygon(polygon)

class PinIndicator(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.pin_pixmap = QPixmap('pin.png')
        if self.pin_pixmap.isNull():
            print("pin.png not found. Pin indicator will not be visible.")
        
        self.resize(16, 16)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.pin_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.pin_pixmap)

class EdgeArrow(QWidget):
    hover_show = pyqtSignal()
    click_toggle_pin = pyqtSignal()
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.is_expanded = False
        self.edge = 'right'
        self.edge_position = 0.5
        self.dragging = False
        self.drag_start_pos = None
        self.is_pinned = False
        
        self.animation_target_expanded = False
        self.mouse_inside = False
        
        self.is_alert = False
        self.alert_opacity = 0.0
        self.alert_increasing = True
        
        self.drag_preview = DragPreview()
        self.pin_indicator = PinIndicator()
        
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.hover_show.emit)
        
        self.expand_animation = QPropertyAnimation(self, b"geometry")
        self.expand_animation.setDuration(150)
        self.expand_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.expand_animation.finished.connect(self.animation_finished)
        
        self.breathing_timer = QTimer()
        self.breathing_timer.timeout.connect(self.update_breathing)
        
        self.screen = QApplication.primaryScreen()
        self.update_sizes_for_edge()
        self.position_on_edge()
        
    def set_alert_state(self, is_alert):
        """Set the alert state and start/stop breathing animation"""
        if self.is_alert != is_alert:
            self.is_alert = is_alert
            if is_alert:
                self.alert_opacity = 0.0
                self.alert_increasing = True
                self.breathing_timer.start(50)
            else:
                self.breathing_timer.stop()
                self.alert_opacity = 0.0
            self.update()
    
    def update_breathing(self):
        """Update breathing animation state"""
        step = 0.05
        if self.alert_increasing:
            self.alert_opacity += step
            if self.alert_opacity >= 1.0:
                self.alert_opacity = 1.0
                self.alert_increasing = False
        else:
            self.alert_opacity -= step
            if self.alert_opacity <= 0.2:
                self.alert_opacity = 0.2
                self.alert_increasing = True
                
        self.update()

    
    def update_sizes_for_edge(self):
        if self.edge in ['top', 'bottom']:
            self.base_size = (60, 30)
            self.expanded_size = (80, 40)
        else:
            self.base_size = (30, 60)
            self.expanded_size = (40, 80)
        
        self.resize(*self.base_size)
        
    def animation_finished(self):
        self.is_expanded = self.animation_target_expanded
        
    def position_on_edge(self):
        if not self.screen:
            self.screen = QApplication.primaryScreen()
        screen_geom = self.screen.geometry()
        
        if self.edge == 'right':
            x = screen_geom.right() - self.width() + 1
            y = screen_geom.y() + int(self.edge_position * (screen_geom.height() - self.height()))
            self.move(x, y)
        elif self.edge == 'left':
            x = screen_geom.x()
            y = screen_geom.y() + int(self.edge_position * (screen_geom.height() - self.height()))
            self.move(x, y)
        elif self.edge == 'top':
            x = screen_geom.x() + int(self.edge_position * (screen_geom.width() - self.width()))
            y = screen_geom.y()
            self.move(x, y)
        elif self.edge == 'bottom':
            x = screen_geom.x() + int(self.edge_position * (screen_geom.width() - self.width()))
            y = screen_geom.bottom() - self.height() + 1
            self.move(x, y)
            
        self.update_pin_indicator_position()
        
    def update_pin_indicator_position(self):
        arrow_pos = self.pos()
        arrow_size = self.size()
        
        if self.edge == 'right':
            pin_x = arrow_pos.x() - 8
            pin_y = arrow_pos.y() - 8
        elif self.edge == 'left':
            pin_x = arrow_pos.x() + arrow_size.width() - 8
            pin_y = arrow_pos.y() - 8
        elif self.edge == 'top':
            pin_x = arrow_pos.x() - 8
            pin_y = arrow_pos.y() + arrow_size.height() - 8
        else:
            pin_x = arrow_pos.x() - 8
            pin_y = arrow_pos.y() - 8
            
        self.pin_indicator.move(pin_x, pin_y)
        
    def set_pinned(self, pinned):
        self.is_pinned = pinned
        if pinned:
            self.update_pin_indicator_position()
            self.pin_indicator.show()
        else:
            self.pin_indicator.hide()
    
    def calculate_edge_and_position(self, global_pos):
        screens = QApplication.screens()
        
        for screen in screens:
            if screen.geometry().contains(global_pos):
                target_screen = screen
                break
        else:
            #find closest screen if cursor is not inside any
            #is your baby crying? i'll make them stop!
            #go to sleeeep go to sleeeep go to sle-e-e-ee-eeep 
            #go to sleep go to sleep googoogaga time for you~

            min_dist = float('inf')
            target_screen = None
            for screen in screens:
                geom = screen.geometry()
                dx = max(0, geom.left() - global_pos.x(), global_pos.x() - geom.right())
                dy = max(0, geom.top() - global_pos.y(), global_pos.y() - geom.bottom())
                dist = dx*dx + dy*dy
                if dist < min_dist:
                    min_dist = dist
                    target_screen = screen

        if not target_screen:
             target_screen = QApplication.primaryScreen()

        geom = target_screen.geometry()
        
        dist_left = abs(global_pos.x() - geom.left())
        dist_right = abs(global_pos.x() - geom.right())
        dist_top = abs(global_pos.y() - geom.top())
        dist_bottom = abs(global_pos.y() - geom.bottom())
        
        min_dist = min(dist_left, dist_right, dist_top, dist_bottom)
        
        if min_dist == dist_left:
            edge = 'left'
            position = max(0, min(1, (global_pos.y() - geom.y()) / geom.height()))
        elif min_dist == dist_right:
            edge = 'right'
            position = max(0, min(1, (global_pos.y() - geom.y()) / geom.height()))
        elif min_dist == dist_top:
            edge = 'top'
            position = max(0, min(1, (global_pos.x() - geom.x()) / geom.width()))
        else:
            edge = 'bottom'
            position = max(0, min(1, (global_pos.x() - geom.x()) / geom.width()))
        
        return edge, position, target_screen
    
    def update_drag_preview(self, global_pos):
        edge, position, screen = self.calculate_edge_and_position(global_pos)
        
        if not screen:
            return

        self.drag_preview.set_edge_and_size(edge)
        
        screen_geom = screen.geometry()
        
        if edge == 'right':
            x = screen_geom.right() - self.drag_preview.width() + 1
            y = screen_geom.y() + int(position * (screen_geom.height() - self.drag_preview.height()))
        elif edge == 'left':
            x = screen_geom.x()
            y = screen_geom.y() + int(position * (screen_geom.height() - self.drag_preview.height()))
        elif edge == 'top':
            x = screen_geom.x() + int(position * (screen_geom.width() - self.drag_preview.width()))
            y = screen_geom.y()
        else: # bottom
            x = screen_geom.x() + int(position * (screen_geom.width() - self.drag_preview.width()))
            y = screen_geom.bottom() - self.drag_preview.height() + 1

        
        self.drag_preview.move(x, y)
        self.drag_preview.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.is_alert:
            bg_color = QColor(CatppuccinTheme.get_color('surface1'))
            accent_color = QColor(CatppuccinTheme.get_color('red'))
            accent_color.setAlphaF(self.alert_opacity)
        elif self.is_expanded or self.mouse_inside:
            bg_color = QColor(CatppuccinTheme.get_color('surface1'))
            accent_color = QColor(CatppuccinTheme.get_color('lavender'))
        else:
            bg_color = QColor(CatppuccinTheme.get_color('surface0'))
            accent_color = QColor(CatppuccinTheme.get_color('blue'))
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(accent_color, 2))
        painter.drawRoundedRect(self.rect(), 8, 8)
        
        if self.is_alert:
            alert_fill = QColor(CatppuccinTheme.get_color('red'))
            alert_fill.setAlphaF(self.alert_opacity * 0.3)
            painter.setBrush(QBrush(alert_fill))
            painter.drawRoundedRect(self.rect(), 8, 8)
        
        painter.setBrush(QBrush(accent_color))
        painter.setPen(QPen(accent_color, 2))
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        if self.edge == 'right':
            points = [(center_x + 5, center_y - 8), (center_x - 5, center_y), (center_x + 5, center_y + 8)]
        elif self.edge == 'left':
            points = [(center_x - 5, center_y - 8), (center_x + 5, center_y), (center_x - 5, center_y + 8)]
        elif self.edge == 'top':
            points = [(center_x - 8, center_y - 5), (center_x, center_y + 5), (center_x + 8, center_y - 5)]
        else:
            points = [(center_x - 8, center_y + 5), (center_x, center_y - 5), (center_x + 8, center_y + 5)]
        
        from PyQt6.QtGui import QPolygon
        polygon = QPolygon([QPoint(x, y) for x, y in points])
        painter.drawPolygon(polygon)
    
    def enterEvent(self, event):
        self.mouse_inside = True
        if not self.animation_target_expanded:
            self.animate_expand(True)
        self.update()
        
        self.hover_timer.start(300)
    
    def leaveEvent(self, event):
        if not self.dragging:
            self.mouse_inside = False
            if self.animation_target_expanded:
                self.animate_expand(False)
            self.update()
        
        self.hover_timer.stop()
    
    def animate_expand(self, expand):
        if self.expand_animation.state() == QPropertyAnimation.State.Running:
            self.expand_animation.stop()
        
        self.animation_target_expanded = expand
        current_rect = self.geometry()
        
        if expand:
            target_size = self.expanded_size
        else:
            target_size = self.base_size
        
        if self.edge in ['left', 'right']:
            width_diff = target_size[0] - current_rect.width()
            height_diff = target_size[1] - current_rect.height()
            new_x = current_rect.x() - (width_diff // 2) if self.edge == 'right' else current_rect.x()
            new_y = current_rect.y() - (height_diff // 2)
        else:
            width_diff = target_size[0] - current_rect.width()
            height_diff = target_size[1] - current_rect.height()
            new_x = current_rect.x() - (width_diff // 2)
            new_y = current_rect.y() - (height_diff // 2) if self.edge == 'bottom' else current_rect.y()
        
        new_rect = QRect(new_x, new_y, target_size[0], target_size[1])
        
        self.expand_animation.setStartValue(current_rect)
        self.expand_animation.setEndValue(new_rect)
        self.expand_animation.start()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_toggle_pin.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint()
            self.drag_started.emit()
            self.drag_preview.show()
            self.update_drag_preview(event.globalPosition().toPoint())
    
    def mouseMoveEvent(self, event):
        if self.dragging and self.drag_start_pos:
            self.update_drag_preview(event.globalPosition().toPoint())
    
    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            self.drag_start_pos = None
            
            self.drag_preview.hide()
            
            edge, position, screen = self.calculate_edge_and_position(event.globalPosition().toPoint())
            
            if screen:
                old_edge = self.edge
                self.edge = edge
                self.edge_position = position
                self.screen = screen
                
                if ((old_edge in ['left', 'right'] and edge in ['top', 'bottom']) or
                    (old_edge in ['top', 'bottom'] and edge in ['left', 'right'])):
                    self.update_sizes_for_edge()
            
            self.position_on_edge()
            self.update()
            
            self.drag_finished.emit()
            
            if not self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
                self.mouse_inside = False
                if self.animation_target_expanded:
                    self.animate_expand(False)

class ProgressBar(QWidget):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.percentage = 0
        self.color = '#89b4fa'
        self.setFixedHeight(8)
        
    def set_percentage(self, percentage):
        self.percentage = max(0, min(100, percentage))
        self.update()
        
    def set_color(self, color):
        self.color = color
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor(CatppuccinTheme.get_color('surface1'))
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)
        
        if self.percentage > 0:
            fill_width = int((self.percentage / 100.0) * self.width())
            fill_rect = QRect(0, 0, fill_width, self.height())
            
            fill_color = QColor(self.color)
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(fill_rect, 4, 4)

class HistoryGraph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.color = '#89b4fa'
        self.setFixedHeight(30)
    
    def set_history(self, history):
        self.history = history
        self.update()
        
    def set_color(self, color):
        self.color = color
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.history:
            return
        
        width = self.width()
        height = self.height()
        
        path = QPainterPath()
        
        points = []
        max_len = 60
        num_points = len(self.history)
        
        for i, val in enumerate(self.history):
            x = (i / max(1, max_len - 1)) * width
            y = height - (val / 100.0) * height
            points.append(QPointF(x, y))
        
        if points:
            path.moveTo(points[0])
            for i in range(len(points) - 1):
                path.lineTo(points[i+1])
        
        pen = QPen(QColor(self.color), 2)
        painter.setPen(pen)
        painter.drawPath(path)

class CompactHud(QWidget):
    hover_show = pyqtSignal()
    drag_finished = pyqtSignal()

    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app = app_instance
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.dragging = False
        self.drag_start_pos = QPoint()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 5, 10, 5)
        self.main_layout.setSpacing(4)
        
        self.cpu_widget = self.create_bar_widget("CPU")
        self.mem_widget = self.create_bar_widget("MEM")
        self.disk_widget = self.create_bar_widget("DSK")

        self.main_layout.addWidget(self.cpu_widget)
        self.main_layout.addWidget(self.mem_widget)
        self.main_layout.addWidget(self.disk_widget)

        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.hover_show.emit)

    def create_bar_widget(self, name):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label = QLabel(f"{name}:")
        label.setStyleSheet(f"color: {CatppuccinTheme.get_color('text')}; font-size: 10px; font-weight: bold;")
        
        bar = ProgressBar()
        bar.setFixedHeight(10)
        
        layout.addWidget(label)
        layout.addWidget(bar, 1)

        widget.setProperty("label", label)
        widget.setProperty("bar", bar)
        return widget

    def update_stats(self, stats, settings):
        # CPU
        if settings['show_cpu']:
            cpu_percent = stats.get('cpu', 0)
            self.cpu_widget.property("bar").set_percentage(cpu_percent)
            self.cpu_widget.property("bar").set_color(CatppuccinTheme.get_color('red'))
            self.cpu_widget.show()
        else:
            self.cpu_widget.hide()

        # Memory
        if settings['show_ram']:
            mem_percent = stats.get('memory', {}).get('percent', 0)
            self.mem_widget.property("bar").set_percentage(mem_percent)
            self.mem_widget.property("bar").set_color(CatppuccinTheme.get_color('blue'))
            self.mem_widget.show()
        else:
            self.mem_widget.hide()

        # Disk
        if settings['show_disk']:
            disk_percent = stats.get('disk', {}).get('percent', 0)
            self.disk_widget.property("bar").set_percentage(disk_percent)
            self.disk_widget.property("bar").set_color(CatppuccinTheme.get_color('green'))
            self.disk_widget.show()
        else:
            self.disk_widget.hide()
            
        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_color = QColor(CatppuccinTheme.get_color('mantle'))
        bg_color.setAlpha(230)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(QColor(CatppuccinTheme.get_color('surface2')), 1))
        painter.drawRoundedRect(self.rect(), 8, 8)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.drag_finished.emit()
            event.accept()

    def enterEvent(self, event):
        self.hover_timer.start(300)

    def leaveEvent(self, event):
        self.hover_timer.stop()



class StatsOverlay(QWidget):
    
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app = app_instance
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.show_cpu = True
        self.show_ram = True
        self.show_disk = True
        self.show_temp = True
        self.show_graphs = True
        self.show_processes = False
        self.show_history = True
        self.current_stats = {}
        self.loading = True
        self.is_pinned = False
        self.ui_setup_complete = False
        self.opacity = 1.0
        self.parent_update_interval = 2.0
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(10)
        
        self.setup_ui()
        self.resize(320, 200)
        self.setWindowOpacity(self.opacity)
        
    def setup_ui(self):
        if self.ui_setup_complete and not self.loading:
            return
            
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
            else:
                sub_layout = item.layout()
                if sub_layout:
                    while sub_layout.count():
                        sub_item = sub_layout.takeAt(0)
                        if sub_item.widget():
                            sub_item.widget().setParent(None)

        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("tarrow")
        title.setStyleSheet(f"""
            QLabel {{
                color: {CatppuccinTheme.get_color('text')};
                font-size: 18px;
                font-weight: bold;
                padding: 5px;
            }}
        """)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.clicked.connect(self.show_settings_immediate)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {CatppuccinTheme.get_color('surface1')};
                color: {CatppuccinTheme.get_color('text')};
                border-radius: 15px;
                padding: 5px;
                font-size: 16px;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {CatppuccinTheme.get_color('surface2')};
            }}
        """)
        header_layout.addWidget(self.settings_btn)
        
        self.main_layout.addLayout(header_layout)
        
        if self.loading:
            loading_label = QLabel("Loading system stats...")
            loading_label.setStyleSheet(f"""
                QLabel {{
                    color: {CatppuccinTheme.get_color('subtext1')};
                    font-size: 14px;
                    padding: 20px;
                    text-align: center;
                }}
            """)
            loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.main_layout.addWidget(loading_label)
            self.ui_setup_complete = False
        else:
            self.stats_widget = QWidget()
            self.stats_layout = QVBoxLayout(self.stats_widget)
            self.stats_layout.setSpacing(8)
            self.main_layout.addWidget(self.stats_widget)
            self.ui_setup_complete = True
        
    def first_load_complete(self):
        self.loading = False
        self.ui_setup_complete = False
        self.setup_ui()
        
    def calculate_content_height(self):
        base_height = 80
        widget_height = 0
        
        if not self.loading and hasattr(self, 'current_stats') and self.current_stats:
            visible_stats = 0
            if self.show_cpu: visible_stats += 1
            if self.show_ram: visible_stats += 1
            if self.show_disk: visible_stats += 1
            
            widget_height += visible_stats * 40 # base for 3 stats
            if self.show_graphs:
                widget_height += visible_stats * 10
            if self.show_history:
                widget_height += visible_stats * 35

            if self.show_temp:
                widget_height += 40

            top_cpu = self.current_stats.get('top_cpu', [])
            top_mem = self.current_stats.get('top_memory', [])
            
            if self.show_processes and top_cpu:
                widget_height += 60 + (len(top_cpu) * 20)
            if self.show_processes and top_mem:
                widget_height += 60 + (len(top_mem) * 20)
        
        return base_height + widget_height
    
    def update_size(self):
        new_height = min(self.calculate_content_height(), 800)
        self.resize(320, new_height)
        
    def update_stats(self, stats):
        self.current_stats = stats
        
        if self.loading:
            return
            
        if hasattr(self, 'stats_layout'):
            for i in reversed(range(self.stats_layout.count())):
                widget = self.stats_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)
        
        if self.show_temp:
            cpu_temp = stats.get('cpu_temp', 'N/A')
            if cpu_temp != "N/A":
                temp_widget = self.create_info_widget("CPU Temp", cpu_temp)
                self.stats_layout.addWidget(temp_widget)

        if self.show_cpu:
            cpu_usage = stats.get('cpu', 0)
            cpu_history = stats.get('cpu_history', [])
            cpu_widget = self.create_stat_widget("CPU Usage", f"{cpu_usage:.2f}%", cpu_usage, 'red', cpu_history)
            self.stats_layout.addWidget(cpu_widget)
        
        if self.show_ram:
            mem_stats = stats.get('memory', {})
            mem_percent = mem_stats.get('percent', 0)
            mem_used = mem_stats.get('used', 0)
            mem_history = stats.get('mem_history', [])
            mem_widget = self.create_stat_widget(
                "Memory", 
                f"{mem_percent:.1f}% ({self.format_bytes(mem_used)})",
                mem_percent,
                'blue',
                mem_history
            )
            self.stats_layout.addWidget(mem_widget)
        
        if self.show_disk:
            disk_stats = stats.get('disk', {})
            disk_percent = disk_stats.get('percent', 0)
            disk_used = disk_stats.get('used', 0)
            disk_history = stats.get('disk_history', [])
            disk_widget = self.create_stat_widget(
                "Disk", 
                f"{disk_percent:.1f}% ({self.format_bytes(disk_used)})",
                disk_percent,
                'green',
                disk_history
            )
            self.stats_layout.addWidget(disk_widget)
        
        top_cpu = stats.get('top_cpu', [])
        top_mem = stats.get('top_memory', [])
        
        if self.show_processes and top_cpu:
            cpu_processes_widget = self.create_processes_widget("Top CPU Processes", top_cpu, 'cpu_percent')
            self.stats_layout.addWidget(cpu_processes_widget)
        
        if self.show_processes and top_mem:
            mem_processes_widget = self.create_processes_widget("Top Memory Processes", top_mem, 'memory_percent')
            self.stats_layout.addWidget(mem_processes_widget)
        
        self.update_size()

    def create_info_widget(self, title, value):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {CatppuccinTheme.get_color('surface0')};
                border-radius: 8px;
                border: 1px solid {CatppuccinTheme.get_color('surface2')};
            }}
        """)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {CatppuccinTheme.get_color('subtext1')}; font-weight: bold; font-size: 13px;")
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {CatppuccinTheme.get_color('text')}; font-size: 13px;")
        
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(value_label)
        
        return widget

    def create_stat_widget(self, title, value, percentage, color_name, history):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {CatppuccinTheme.get_color('surface0')};
                border-radius: 8px;
                border: 1px solid {CatppuccinTheme.get_color('surface2')};
            }}
        """)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {CatppuccinTheme.get_color('subtext1')};
                font-weight: bold;
                font-size: 13px;
            }}
        """)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"""
            QLabel {{
                color: {CatppuccinTheme.get_color('text')};
                font-size: 13px;
            }}
        """)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(value_label)
        layout.addLayout(header_layout)
        
        if self.show_graphs:
            progress_bar = ProgressBar()
            progress_bar.set_percentage(percentage)
            progress_bar.set_color(CatppuccinTheme.get_color(color_name))
            layout.addWidget(progress_bar)

        if self.show_history:
            history_graph = HistoryGraph()
            history_graph.set_history(history)
            history_graph.set_color(CatppuccinTheme.get_color(color_name))
            layout.addWidget(history_graph)
        
        return widget
    
    def create_processes_widget(self, title, processes, sort_key):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {CatppuccinTheme.get_color('surface0')};
                border-radius: 8px;
                border: 1px solid {CatppuccinTheme.get_color('surface2')};
            }}
        """)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {CatppuccinTheme.get_color('subtext1')};
                font-weight: bold;
                font-size: 13px;
                margin-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)
        
        for i, proc in enumerate(processes[:3]):
            proc_value = proc.get(sort_key, 0)
            if proc_value is None or proc_value <= 0:
                continue
                
            proc_layout = QHBoxLayout()
            proc_layout.setContentsMargins(0, 2, 0, 2)
            
            proc_name = proc.get('name', 'Unknown')
            if len(proc_name) > 25:
                proc_name = proc_name[:22] + '...'
                
            name_label = QLabel(proc_name)
            name_label.setStyleSheet(f"""
                QLabel {{
                    color: {CatppuccinTheme.get_color('text')};
                    font-size: 11px;
                }}
            """)
            
            value_label = QLabel(f"{proc_value:.1f}%")
            value_label.setStyleSheet(f"""
                QLabel {{
                    color: {CatppuccinTheme.get_color('blue')};
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
            
            proc_layout.addWidget(name_label)
            proc_layout.addStretch()
            proc_layout.addWidget(value_label)
            layout.addLayout(proc_layout)
        
        return widget
    
    def format_bytes(self, bytes_val):
        if bytes_val == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
    
    def show_settings_immediate(self):
        QTimer.singleShot(0, self._create_and_show_settings)
    
    def _create_and_show_settings(self):
        if not hasattr(self, 'settings_dialog') or not self.settings_dialog.isVisible():
            self.settings_dialog = SettingsDialog(self.app)
            self.settings_dialog.cpu_changed.connect(self.change_cpu_visibility)
            self.settings_dialog.ram_changed.connect(self.change_ram_visibility)
            self.settings_dialog.disk_changed.connect(self.change_disk_visibility)
            self.settings_dialog.temp_changed.connect(self.change_temp_visibility)
            self.settings_dialog.graphs_changed.connect(self.change_graphs)
            self.settings_dialog.processes_changed.connect(self.change_processes)
            self.settings_dialog.history_changed.connect(self.change_history)
            self.settings_dialog.interval_changed.connect(self.change_interval)
            self.settings_dialog.opacity_changed.connect(self.change_opacity)
            self.settings_dialog.hotkey_change_requested.connect(self.app.on_hotkey_change_request)
            self.settings_dialog.compact_mode_changed.connect(self.app.on_compact_mode_changed)

        self.settings_dialog.set_current_values(
            self.show_cpu, self.show_ram, self.show_disk, self.show_temp,
            self.show_graphs, self.show_processes, self.show_history, self.parent_update_interval,
            self.app.hotkey_name, self.app.compact_mode
        )
        self.settings_dialog.set_current_opacity(self.opacity)
        if hasattr(self.app, "alert_threshold"):
            self.settings_dialog.set_alert_threshold(self.app.alert_threshold)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
    
    def change_cpu_visibility(self, show):
        self.show_cpu = show
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)

    def change_ram_visibility(self, show):
        self.show_ram = show
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)

    def change_disk_visibility(self, show):
        self.show_disk = show
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)

    def change_temp_visibility(self, show):
        self.show_temp = show
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)

    def change_graphs(self, show_graphs):
        self.show_graphs = show_graphs
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)
    
    def change_processes(self, show_processes):
        self.show_processes = show_processes
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)

    def change_history(self, show_history):
        self.show_history = show_history
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats(self.current_stats)
    
    def change_interval(self, interval):
        pass

    def change_opacity(self, opacity):
        self.opacity = opacity
        self.setWindowOpacity(opacity)
        if hasattr(self.app, 'save_settings'):
            self.app.save_settings()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor(CatppuccinTheme.get_color('base'))
        bg_color.setAlpha(245)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(QColor(CatppuccinTheme.get_color('surface2')), 2))
        painter.drawRoundedRect(self.rect(), 12, 12)

class SettingsDialog(QWidget):
    cpu_changed = pyqtSignal(bool)
    ram_changed = pyqtSignal(bool)
    disk_changed = pyqtSignal(bool)
    temp_changed = pyqtSignal(bool)
    graphs_changed = pyqtSignal(bool)
    processes_changed = pyqtSignal(bool)
    history_changed = pyqtSignal(bool)
    interval_changed = pyqtSignal(float)
    opacity_changed = pyqtSignal(float)
    alert_threshold_changed = pyqtSignal(float)
    hotkey_change_requested = pyqtSignal()
    compact_mode_changed = pyqtSignal(bool)
    
    def __init__(self, app_instance, parent=None):
        super().__init__(parent)
        self.app = app_instance
        self.setWindowTitle("tarrow")
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.resize(400, 350)
        self.current_show_cpu = self.app.show_cpu
        self.current_show_ram = self.app.show_ram
        self.current_show_disk = self.app.show_disk
        self.current_show_temp = self.app.show_temp
        self.current_show_graphs = self.app.show_graphs
        self.current_show_processes = self.app.show_processes
        self.current_show_history = self.app.show_history
        self.current_interval = self.app.update_interval
        self.current_opacity = self.app.overlay_opacity
        self.current_threshold = self.app.alert_threshold
        self.current_hotkey = self.app.hotkey_name
        self.current_compact_mode = self.app.compact_mode

        self.setup_ui()
        
    def setup_ui(self):
        if not self.layout():
            layout = QVBoxLayout(self)
        else:
            layout = self.layout()
            for i in reversed(range(layout.count())):
                child = layout.itemAt(i).widget()
                if child:
                    child.setParent(None)
        
        self.compact_mode_checkbox = QCheckBox("Compact HUD Mode")
        self.compact_mode_checkbox.setChecked(self.current_compact_mode)
        self.compact_mode_checkbox.toggled.connect(self.on_compact_mode_changed)
        layout.addWidget(self.compact_mode_checkbox)

        self.cpu_checkbox = QCheckBox("Show CPU Usage")
        self.cpu_checkbox.setChecked(self.current_show_cpu)
        self.cpu_checkbox.toggled.connect(self.on_cpu_changed_immediate)
        layout.addWidget(self.cpu_checkbox)

        self.ram_checkbox = QCheckBox("Show Memory Usage")
        self.ram_checkbox.setChecked(self.current_show_ram)
        self.ram_checkbox.toggled.connect(self.on_ram_changed_immediate)
        layout.addWidget(self.ram_checkbox)

        self.disk_checkbox = QCheckBox("Show Disk Usage")
        self.disk_checkbox.setChecked(self.current_show_disk)
        self.disk_checkbox.toggled.connect(self.on_disk_changed_immediate)
        layout.addWidget(self.disk_checkbox)

        self.temp_checkbox = QCheckBox("Show CPU Temperature")
        self.temp_checkbox.setChecked(self.current_show_temp)
        self.temp_checkbox.toggled.connect(self.on_temp_changed_immediate)
        layout.addWidget(self.temp_checkbox)

        self.graphs_checkbox = QCheckBox("Show Progress Bars")
        self.graphs_checkbox.setChecked(self.current_show_graphs)
        self.graphs_checkbox.toggled.connect(self.on_graphs_changed_immediate)
        layout.addWidget(self.graphs_checkbox)
        
        self.history_checkbox = QCheckBox("Show History Graphs")
        self.history_checkbox.setChecked(self.current_show_history)
        self.history_checkbox.toggled.connect(self.on_history_changed_immediate)
        layout.addWidget(self.history_checkbox)

        self.processes_checkbox = QCheckBox("Show Top Processes")
        self.processes_checkbox.setChecked(self.current_show_processes)
        self.processes_checkbox.toggled.connect(self.on_processes_changed_immediate)
        layout.addWidget(self.processes_checkbox)
        
        self.hotkey_button = QPushButton(f"Hotkey: {self.current_hotkey}")
        self.hotkey_button.clicked.connect(self.request_hotkey_change)
        layout.addWidget(self.hotkey_button)

        interval_layout = QHBoxLayout()
        interval_label = QLabel("Update Interval (seconds):")
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 10.0)
        self.interval_spin.setSingleStep(0.1)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setValue(self.current_interval)
        
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(self.interval_spin)
        layout.addLayout(interval_layout)
        
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Alert Threshold (%):")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(50.0, 100.0)
        self.threshold_spin.setSingleStep(1.0)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setValue(self.current_threshold)
        
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spin)
        layout.addLayout(threshold_layout)
        
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel("Overlay Opacity:")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(self.current_opacity * 100))
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.opacity_value_label = QLabel(f"{self.current_opacity:.2f}")
        opacity_layout.addWidget(opacity_label)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_value_label)
        layout.addLayout(opacity_layout)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(apply_btn)
        
    def set_current_values(self, show_cpu, show_ram, show_disk, show_temp, show_graphs, show_processes, show_history, interval, hotkey, compact_mode):
        self.current_show_cpu = show_cpu
        self.current_show_ram = show_ram
        self.current_show_disk = show_disk
        self.current_show_temp = show_temp
        self.current_show_graphs = show_graphs
        self.current_show_processes = show_processes
        self.current_show_history = show_history
        self.current_interval = float(interval)
        self.current_hotkey = hotkey
        self.current_compact_mode = compact_mode

        if hasattr(self, 'cpu_checkbox'): self.cpu_checkbox.setChecked(show_cpu)
        if hasattr(self, 'ram_checkbox'): self.ram_checkbox.setChecked(show_ram)
        if hasattr(self, 'disk_checkbox'): self.disk_checkbox.setChecked(show_disk)
        if hasattr(self, 'temp_checkbox'): self.temp_checkbox.setChecked(show_temp)
        if hasattr(self, 'graphs_checkbox'): self.graphs_checkbox.setChecked(show_graphs)
        if hasattr(self, 'processes_checkbox'): self.processes_checkbox.setChecked(show_processes)
        if hasattr(self, 'history_checkbox'): self.history_checkbox.setChecked(show_history)
        if hasattr(self, 'interval_spin'): self.interval_spin.setValue(self.current_interval)
        if hasattr(self, 'hotkey_button'): self.hotkey_button.setText(f"Hotkey: {hotkey}")
        if hasattr(self, 'compact_mode_checkbox'): self.compact_mode_checkbox.setChecked(compact_mode)

    def update_hotkey_display(self, key_name):
        self.current_hotkey = key_name
        self.hotkey_button.setText(f"Hotkey: {key_name}")

    def request_hotkey_change(self):
        self.hotkey_button.setText("Press any key...")
        self.hotkey_change_requested.emit()


    def set_current_opacity(self, opacity):
        self.current_opacity = opacity
        if hasattr(self, "opacity_slider"):
            self.opacity_slider.setValue(int(opacity * 100))
        if hasattr(self, "opacity_value_label"):
            self.opacity_value_label.setText(f"{opacity:.2f}")

    def set_alert_threshold(self, threshold):
        self.current_threshold = threshold
        if hasattr(self, 'threshold_spin'):
            self.threshold_spin.setValue(threshold)

    def on_compact_mode_changed(self, checked): self.compact_mode_changed.emit(checked)
    def on_cpu_changed_immediate(self, checked): self.cpu_changed.emit(checked)
    def on_ram_changed_immediate(self, checked): self.ram_changed.emit(checked)
    def on_disk_changed_immediate(self, checked): self.disk_changed.emit(checked)
    def on_temp_changed_immediate(self, checked): self.temp_changed.emit(checked)
    def on_graphs_changed_immediate(self, checked): self.graphs_changed.emit(checked)
    def on_processes_changed_immediate(self, checked): self.processes_changed.emit(checked)
    def on_history_changed_immediate(self, checked): self.history_changed.emit(checked)

    def on_opacity_changed(self, value):
        opacity = value / 100.0
        self.current_opacity = opacity
        self.opacity_value_label.setText(f"{opacity:.2f}")
        self.opacity_changed.emit(opacity)

    def apply_settings(self):
        self.interval_changed.emit(self.interval_spin.value())
        self.opacity_changed.emit(self.current_opacity)
        self.alert_threshold_changed.emit(self.threshold_spin.value())
        self.close()

class OverlayEventFilter(QObject):
    overlay_leave = pyqtSignal()
    overlay_enter = pyqtSignal()
    overlay_click = pyqtSignal()
    
    def eventFilter(self, obj, event):
        if event.type() == event.Type.Leave:
            self.overlay_leave.emit()
        elif event.type() == event.Type.Enter:
            self.overlay_enter.emit()
        elif event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.overlay_click.emit()
        
        return False

class tarrow(QObject):
    hotkey_has_been_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        self.show_cpu = True
        self.show_ram = True
        self.show_disk = True
        self.show_temp = True
        self.show_graphs = True
        self.show_processes = True
        self.show_history = True
        self.update_interval = 2.0
        self.overlay_opacity = 1.0
        self.high_resource_usage = False
        self.alert_threshold = 95.0
        self.hotkey_name = 'f13'
        self.hotkey_listener = None
        self.hotkey_is_down = False
        self.compact_mode = False

        self.arrow = EdgeArrow()
        self.arrow.hover_show.connect(self.show_overlay_on_hover)
        self.arrow.click_toggle_pin.connect(self.toggle_pin_overlay)
        self.arrow.drag_started.connect(self.on_drag_started)
        self.arrow.drag_finished.connect(self.save_settings)
        
        self.compact_hud = CompactHud(self)
        self.compact_hud.hover_show.connect(self.show_overlay_on_hover)
        self.compact_hud.drag_finished.connect(self.save_settings)
        
        self.overlay = StatsOverlay(app_instance=self)
        self.overlay_visible = False
        
        self.overlay_filter = OverlayEventFilter()
        self.overlay_filter.overlay_leave.connect(self.on_overlay_leave)
        self.overlay_filter.overlay_enter.connect(self.on_overlay_enter)
        self.overlay_filter.overlay_click.connect(self.on_overlay_click)
        
        self.hover_check_timer = QTimer()
        self.hover_check_timer.timeout.connect(self.check_hover_state)
        self.hover_check_timer.start(100)
        
        self.stats_worker = SystemStatsWorker()
        self.stats_worker.stats_updated.connect(self.update_stats)
        self.stats_worker.first_load_complete.connect(self.overlay.first_load_complete)
        self.stats_worker.start()

        self.load_settings()
        self.update_hud_mode()
        self.setup_hotkey_listener()
        self.overlay.setWindowOpacity(self.overlay_opacity)
        self.overlay.opacity = self.overlay_opacity
        self.overlay.parent_update_interval = self.update_interval

    def setup_hotkey_listener(self):
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener.wait()

        self.hotkey_listener = HotkeyListener(self.hotkey_name)
        self.hotkey_listener.hotkey_pressed.connect(self.show_overlay_on_hotkey)
        self.hotkey_listener.hotkey_released.connect(self.hide_overlay_on_hotkey)
        self.hotkey_listener.hotkey_captured.connect(self.on_hotkey_captured)
        self.hotkey_listener.start()

    def update_stats(self, stats):
        settings = {
            'show_cpu': self.show_cpu,
            'show_ram': self.show_ram,
            'show_disk': self.show_disk,
        }
        if self.compact_mode and self.compact_hud.isVisible():
            self.compact_hud.update_stats(stats, settings)

        if self.overlay_visible:
            self.overlay.update_stats(stats)
        
        cpu_usage = stats.get('cpu', 0)
        mem_stats = stats.get('memory', {})
        mem_percent = mem_stats.get('percent', 0)
        
        is_high_usage = (cpu_usage >= self.alert_threshold or mem_percent >= self.alert_threshold)
        
        if is_high_usage != self.high_resource_usage:
            self.high_resource_usage = is_high_usage
            if not self.compact_mode:
                self.arrow.set_alert_state(is_high_usage)

    def on_hotkey_change_request(self):
        if self.hotkey_listener:
            self.hotkey_listener.enter_capture_mode()

    def on_hotkey_captured(self, key_name):
        self.hotkey_name = key_name
        self.setup_hotkey_listener()
        self.hotkey_has_been_updated.emit(key_name)
        self.save_settings()

    def show_overlay_on_hotkey(self):
        self.hotkey_is_down = True
        if not self.overlay_visible:
            self.position_and_show_overlay()

    def hide_overlay_on_hotkey(self):
        self.hotkey_is_down = False
        if not self.overlay.is_pinned:
            self.overlay.hide()
            self.overlay_visible = False


    def check_hover_state(self):
        if not self.overlay_visible or self.overlay.is_pinned or self.hotkey_is_down:
            return
        
        cursor_pos = QCursor.pos()
        
        if self.compact_mode:
            trigger_widget = self.compact_hud
        else:
            trigger_widget = self.arrow
            
        trigger_rect = QRect(trigger_widget.pos(), trigger_widget.size())
        cursor_over_trigger = trigger_rect.contains(cursor_pos)
        
        overlay_rect = QRect(self.overlay.pos(), self.overlay.size())
        cursor_over_overlay = overlay_rect.contains(cursor_pos)
        
        if not cursor_over_trigger and not cursor_over_overlay:
            self.overlay.hide()
            self.overlay_visible = False
    def show_overlay_on_hover(self):
        if not self.overlay_visible:
            self.position_and_show_overlay()
    def toggle_pin_overlay(self):
        new_pinned = not self.overlay.is_pinned
        self.overlay.is_pinned = new_pinned
        if not self.compact_mode:
            self.arrow.set_pinned(new_pinned)
        if not self.overlay_visible:
            self.position_and_show_overlay()
    def on_drag_started(self):
        if self.overlay_visible:
            self.overlay.hide()
            self.overlay_visible = False
    def on_drag_finished(self):
        self.save_settings()
        if self.overlay.is_pinned:
            self.position_and_show_overlay()

    def position_and_show_overlay(self):
        if self.compact_mode:
            trigger_widget = self.compact_hud
            screen = trigger_widget.screen()
        else:
            trigger_widget = self.arrow
            screen = trigger_widget.screen
        
        screen_geom = screen.geometry()
        trigger_pos = trigger_widget.pos()
        trigger_size = trigger_widget.size()
        
        overlay_x = trigger_pos.x() + trigger_size.width() + 10
        overlay_y = trigger_pos.y() + (trigger_size.height() // 2) - (self.overlay.height() // 2)

        
        self.overlay.move(overlay_x, overlay_y)
        
        overlay_rect = self.overlay.geometry()
        if overlay_rect.right() > screen_geom.right():
            self.overlay.move(screen_geom.right() - self.overlay.width(), overlay_rect.y())
        if overlay_rect.left() < screen_geom.left():
            self.overlay.move(screen_geom.left(), overlay_rect.y())
        if overlay_rect.bottom() > screen_geom.bottom():
            self.overlay.move(overlay_rect.x(), screen_geom.bottom() - self.overlay.height())
        if overlay_rect.top() < screen_geom.top():
            self.overlay.move(overlay_rect.x(), screen_geom.top())

        self.overlay.show()
        self.overlay_visible = True
        self.overlay.installEventFilter(self.overlay_filter)
    def on_overlay_leave(self):
        pass
    def on_overlay_enter(self):
        pass
    def on_overlay_click(self):
        pass
    def load_settings(self):
        settings_file = Path.home() / '.tarrow.json'
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                
                self.compact_mode = settings.get('compact_mode', False)
                pos = settings.get('compact_hud_pos')
                if pos:
                    self.compact_hud.move(QPoint(pos[0], pos[1]))
                
                screen_name = settings.get('screen_name')
                screens = self.app.screens()
                target_screen = None
                if screen_name:
                    for s in screens:
                        if s.name() == screen_name:
                            target_screen = s
                            break
                self.arrow.screen = target_screen or self.app.primaryScreen()

                self.arrow.edge = settings.get('edge', 'right')
                self.arrow.edge_position = settings.get('edge_position', 0.5)
                self.arrow.update_sizes_for_edge()
                self.arrow.position_on_edge()
                
                self.show_cpu = settings.get('show_cpu', True)
                self.show_ram = settings.get('show_ram', True)
                self.show_disk = settings.get('show_disk', True)
                self.show_temp = settings.get('show_temp', True)
                self.show_graphs = settings.get('show_graphs', True)
                self.show_processes = settings.get('show_processes', True)
                self.show_history = settings.get('show_history', True)
                self.update_interval = float(settings.get('update_interval', 2.0))
                self.overlay_opacity = float(settings.get('overlay_opacity', 1.0))
                self.alert_threshold = float(settings.get('alert_threshold', 95.0))
                self.hotkey_name = settings.get('hotkey', 'f13')

                self.overlay.show_cpu = self.show_cpu
                self.overlay.show_ram = self.show_ram
                self.overlay.show_disk = self.show_disk
                self.overlay.show_temp = self.show_temp
                self.overlay.show_graphs = self.show_graphs
                self.overlay.show_processes = self.show_processes
                self.overlay.show_history = self.show_history
                self.stats_worker.set_update_interval(self.update_interval)
                self.overlay.opacity = self.overlay_opacity
                self.overlay.setWindowOpacity(self.overlay_opacity)
                self.overlay.parent_update_interval = self.update_interval
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        settings = {
            'screen_name': self.arrow.screen.name() if self.arrow.screen else '',
            'edge': self.arrow.edge,
            'edge_position': self.arrow.edge_position,
            'compact_mode': self.compact_mode,
            'compact_hud_pos': [self.compact_hud.x(), self.compact_hud.y()],
            'show_cpu': self.show_cpu,
            'show_ram': self.show_ram,
            'show_disk': self.show_disk,
            'show_temp': self.show_temp,
            'show_graphs': self.show_graphs,
            'show_processes': self.show_processes,
            'show_history': self.show_history,
            'update_interval': float(self.update_interval),
            'overlay_opacity': float(self.overlay.opacity if hasattr(self.overlay, "opacity") else 1.0),
            'alert_threshold': float(self.alert_threshold),
            'hotkey': self.hotkey_name
        }

        settings_file = Path.home() / '.tarrow.json'
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def on_compact_mode_changed(self, enabled):
        self.compact_mode = enabled
        self.update_hud_mode()
        self.save_settings()

    def update_hud_mode(self):
        if self.compact_mode:
            self.arrow.hide()
            self.compact_hud.show()
        else:
            self.compact_hud.hide()
            self.arrow.show()

    def on_cpu_changed(self, show):
        self.show_cpu = show
        self.overlay.change_cpu_visibility(show)
        self.save_settings()

    def on_ram_changed(self, show):
        self.show_ram = show
        self.overlay.change_ram_visibility(show)
        self.save_settings()

    def on_disk_changed(self, show):
        self.show_disk = show
        self.overlay.change_disk_visibility(show)
        self.save_settings()

    def on_temp_changed(self, show):
        self.show_temp = show
        self.overlay.change_temp_visibility(show)
        self.save_settings()

    def on_graphs_changed(self, show_graphs):
        self.show_graphs = show_graphs
        self.overlay.change_graphs(show_graphs)
        self.save_settings()

    def on_processes_changed(self, show_processes):
        self.show_processes = show_processes
        self.overlay.change_processes(show_processes)
        self.save_settings()

    def on_history_changed(self, show_history):
        self.show_history = show_history
        self.overlay.change_history(show_history)
        self.save_settings()
    
    def on_interval_changed(self, interval):
        self.update_interval = float(interval)
        self.stats_worker.set_update_interval(interval)
        self.overlay.parent_update_interval = self.update_interval
        self.save_settings()
    def on_opacity_changed(self, opacity):
        self.overlay_opacity = opacity
        self.overlay.opacity = opacity
        self.overlay.setWindowOpacity(opacity)
        self.save_settings()

    def on_alert_threshold_changed(self, threshold):
        self.alert_threshold = float(threshold)
        self.save_settings()
        
    def run(self):
        try:
            return self.app.exec()
        finally:
            if hasattr(self, 'stats_worker'):
                self.stats_worker.stop()
            if hasattr(self, 'hotkey_listener'):
                self.hotkey_listener.stop()
            self.save_settings()

if __name__ == "__main__":
    app = tarrow()

    def connect_settings_signals(overlay):
        if hasattr(overlay, 'settings_dialog') and overlay.settings_dialog:
            overlay.settings_dialog.set_current_values(
                app.show_cpu, app.show_ram, app.show_disk, app.show_temp,
                app.show_graphs, app.show_processes, app.show_history, app.update_interval,
                app.hotkey_name, app.compact_mode
            )
            overlay.settings_dialog.set_current_opacity(app.overlay.opacity if hasattr(app.overlay, "opacity") else 1.0)
            overlay.settings_dialog.set_alert_threshold(app.alert_threshold)
            overlay.settings_dialog.cpu_changed.connect(app.on_cpu_changed)
            overlay.settings_dialog.ram_changed.connect(app.on_ram_changed)
            overlay.settings_dialog.disk_changed.connect(app.on_disk_changed)
            overlay.settings_dialog.temp_changed.connect(app.on_temp_changed)
            overlay.settings_dialog.graphs_changed.connect(app.on_graphs_changed)
            overlay.settings_dialog.processes_changed.connect(app.on_processes_changed)
            overlay.settings_dialog.history_changed.connect(app.on_history_changed)
            overlay.settings_dialog.interval_changed.connect(app.on_interval_changed)
            overlay.settings_dialog.opacity_changed.connect(app.on_opacity_changed)
            overlay.settings_dialog.alert_threshold_changed.connect(app.on_alert_threshold_changed)
            app.hotkey_has_been_updated.connect(overlay.settings_dialog.update_hotkey_display)

    original_show_settings = app.overlay.show_settings_immediate
    def enhanced_show_settings():
        original_show_settings()
        QTimer.singleShot(50, lambda: connect_settings_signals(app.overlay))
    app.overlay.show_settings_immediate = enhanced_show_settings

    sys.exit(app.run())