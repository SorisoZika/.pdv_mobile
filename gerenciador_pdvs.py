import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QDialog, QMessageBox, QGridLayout, QSizePolicy,
                             QCheckBox, QScrollArea, QProgressBar, QTextEdit)
from PyQt5.QtGui import QFont, QMovie
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from datetime import date
import paramiko
import subprocess
import threading
import platform
import shutil
import webbrowser
import os
import concurrent.futures
import pyperclip
import time

# ========== CONFIGURAÇÃO ==========
IP_INICIAL = 101
IP_FINAL = 132
EXCLUIR_PDVS = [131]
ADICIONAIS = {"172.23.128.100": 100}
BASE_IP = "172.23.128."
USUARIO_PADRAO = "suporte"
FONTE_PADRAO = QFont("Arial", 12)
FONTE_BOTOES = QFont("Arial", 13) # Usaremos essa fonte para o ComboBox e QLabel de Visualização

# ========== FUNÇÕES ==========
def gerar_senha(ip): # type: ignore
    ultimo_num = int(ip.split('.')[-1]) # type: ignore
    if ip in ADICIONAIS and ADICIONAIS[ip] == 100:
        pdv_num = 999
    else:
        pdv_num = ultimo_num - 100
    hoje = date.today()
    valor = int(str(hoje.day) + str(hoje.month)) + pdv_num
    return f"pdv@{valor}", pdv_num

def executar_comando(ip, usuario, senha, comando): # type: ignore
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=usuario, password=senha, timeout=5) # type: ignore
        # Para comandos que reiniciam, o timeout pode ser mais curto, pois não esperamos uma resposta completa
        timeout_exec = 30 if "reboot" in comando else 10
        comando_sudo = f'echo "{senha}" | sudo -S {comando}'
        stdin, stdout, stderr = ssh.exec_command(comando_sudo, timeout=timeout_exec) # type: ignore
        saida = stdout.read().decode()
        erro = stderr.read().decode()
        ssh.close()
        # Para o comando de reboot, a saída pode estar vazia ou a conexão pode cair, o que é normal.
        if "reboot" in comando and not erro:
            return "Comando de reinicialização enviado."
        return saida if saida else erro
    except Exception as e:
        # Se o comando era de reboot, uma exceção de "Socket is closed" ou similar é esperada e normal.
        if "reboot" in comando and isinstance(e, paramiko.SSHException):
            return "Comando de reinicialização enviado com sucesso (a conexão foi encerrada como esperado)."
        return str(e)

def abrir_vnc(ip):
    try:
        vnc_path = r"C:\Program Files\RealVNC\VNC Viewer\vncviewer.exe"
        if not os.path.exists(vnc_path):
            QMessageBox.critical(None, "Erro", f"VNC Viewer não encontrado em:\n{vnc_path}\nVerifique a instalação.")
            return

        senha, _ = gerar_senha(ip)
        pyperclip.copy(senha)  # Copia a senha para a área de transferência

        # Abre o VNC Viewer
        subprocess.Popen([vnc_path, ip])

        # Aguarda um tempo para a janela do VNC Viewer abrir
        time.sleep(3)

        # Executa o script AutoHotkey
        try:
            subprocess.Popen(["C:\\Program Files\\AutoHotkey\\AutoHotkey.exe", "vnc_automation.ahk"])
        except Exception as e:
            QMessageBox.critical(None, "Erro", f"Erro ao executar AutoHotkey: {str(e)}")

    except Exception as e:
        QMessageBox.critical(None, "Erro", f"Erro ao tentar abrir VNC Viewer: {str(e)}")

def is_pdv_online(ip, timeout=1):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    comando = ['ping', param, '1', ip]
    try:
        return subprocess.call(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 2) == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

# ========== SINAL PARA ATUALIZAR UI ==========
class Communicate(QObject):
    update_status = pyqtSignal(list, int, int)
    update_message = pyqtSignal(str)
    show_info_box = pyqtSignal(str, str, QWidget)
    show_error_box = pyqtSignal(str, str, QWidget)

# ========== BOTÃO PDV ==========
class PDVButton(QPushButton):
    def __init__(self, label, ip=None, parent=None): # ip is now optional
        super().__init__(label, parent)
        self.ip = ip # can be None for non-PDV buttons
        self.offline = False
        self.setFont(FONTE_BOTOES)
        self.setMinimumSize(140, 80)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.update_style()

    def set_offline(self, offline):
        self.offline = offline
        self.update_style()

    def update_style(self):
        # Only apply offline styling if it's a PDV button (has an IP)
        if self.ip:
            bg_color = "#f7c5c5" if self.offline else "#c5f7c8"
        else: # For non-PDV buttons like MaxiPos, use a neutral color
            bg_color = "#d3d3d3" if not self.offline else "#c5f7c8" # Neutral gray for non-PDV, or same as online PDV if it doesn't represent status
            
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color}; padding: 8px 10px; border-radius: 4px;
                font-size: 15px; color: black; border: none;
            }}
            QPushButton:hover {{ background-color: #aaa; }}
        """)

# ========== JANELA DE LOGIN ==========
class LoginDialog(QDialog):
    def __init__(self, ip, pdv_num, main_window_ref):
        super().__init__(None, Qt.Window)
        print(f"DEBUG: LoginDialog.__init__ called for PDV {pdv_num} ({ip}).")
        self.setWindowTitle(f"Conectar ao PDV {pdv_num}")
        self.resize(400, 220)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(main_window_ref.styleSheet()) # Herda o estilo da janela principal
        self.ip = ip
        self.pdv_num = pdv_num
        self.main_window_ref = main_window_ref

        layout = QVBoxLayout()

        label_usuario = QLabel("Usuário:")
        label_usuario.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_usuario)
        self.usuario_edit = QLineEdit(USUARIO_PADRAO)
        layout.addWidget(self.usuario_edit)

        label_senha = QLabel("Senha:")
        label_senha.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_senha)
        
        senha_layout = QHBoxLayout()
        self.senha, _ = gerar_senha(ip)
        self.senha_edit = QLineEdit(self.senha)
        self.senha_edit.setEchoMode(QLineEdit.Password)
        self.senha_edit.setMinimumHeight(30)

        self.toggle_senha_btn = QPushButton()
        self.toggle_senha_btn.setText("👁️")
        self.toggle_senha_btn.setFont(QFont("Segoe UI Symbol", 12))
        self.toggle_senha_btn.setFixedSize(30, 30)
        self.toggle_senha_btn.clicked.connect(self.toggle_senha_visibility)
        self.senha_visivel = False

        senha_layout.addWidget(self.senha_edit)
        senha_layout.addWidget(self.toggle_senha_btn)
        layout.addLayout(senha_layout)

        btn_conectar = QPushButton("Conectar 🔐")
        btn_conectar.clicked.connect(self.conectar)
        layout.addWidget(btn_conectar)

        self.setLayout(layout)
        QApplication.clipboard().setText(self.senha)

        btn_conectar.setDefault(True)
        self.usuario_edit.setFocus()


    def toggle_senha_visibility(self):
        if self.senha_visivel:
            self.senha_edit.setEchoMode(QLineEdit.Password)
            self.toggle_senha_btn.setText("👁️")
        else:
            self.senha_edit.setEchoMode(QLineEdit.Normal)
            self.toggle_senha_btn.setText("🔒")
        self.senha_visivel = not self.senha_visivel

    def conectar(self):
        print("DEBUG: LoginDialog.conectar method called (inside dialog).")
        usuario = self.usuario_edit.text()
        senha = self.senha_edit.text()
        resultado = executar_comando(self.ip, usuario, senha, "echo Conexao OK")
        if "Conexao OK" in resultado:
            self.accept()
            print(f"DEBUG: LoginDialog accepted.")
            # Passa a preferência de visualização para a janela de comandos
            self.main_window_ref.abrir_comandos(self.ip, usuario, senha, self.pdv_num, "Lista")
        else:
            print(f"DEBUG: LoginDialog connection failed: {resultado}")
            QMessageBox.critical(self, "Erro", f"Falha ao conectar: {resultado}")

# ========== JANELA DE SELEÇÃO DE PDVs ==========
class CheckBoxPDV(QCheckBox):
    def __init__(self, label, ip, parent=None):
        super().__init__(label, parent)
        self.ip = ip # Adiciona o IP ao checkbox

class SelecionarPDVsDialog(QDialog):
    def __init__(self, lista_pdvs, main_window_ref):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Selecionar PDVs para abrir no navegador")
        self.resize(500, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(main_window_ref.styleSheet())
        self.lista_pdvs = lista_pdvs
        self.checkboxes = []
        self.main_window_ref = main_window_ref

        layout = QVBoxLayout()
        top_layout = QHBoxLayout()

        self.checkbox_todos = QCheckBox("Selecionar Todos")
        # Estilo para os QCheckBoxes do topo (com borda) - TAMANHO AJUSTADO E INDICADOR VISÍVEL
        self.checkbox_todos.setStyleSheet("""
            QCheckBox {
                background-color: transparent;
                border: 1px solid #777;
                border-radius: 3px;
                padding: 10px 15px;
                color: #f0f0f0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #FFFFFF; /* MODIFICADO: Borda branca para melhor contraste */
                border-radius: 3px;
                background-color: #3e3e3e;
            }
            QCheckBox::indicator:checked {
                background-color: white; 
                border: 1px solid #FFFFFF;   
            }
        """)
        self.checkbox_todos.stateChanged.connect(self.selecionar_todos)
        top_layout.addWidget(self.checkbox_todos)

        self.faixas = {"1 ao 10": (1, 10), "11 ao 20": (11, 20), "21 ao 32": (21, 32)}
        self.checkbox_faixas = {}
        for label, (inicio, fim) in self.faixas.items():
            cb = QCheckBox(label)
            # Estilo para os QCheckBoxes de faixa (com borda) - TAMANHO AJUSTADO E INDICADOR VISÍVEL
            cb.setStyleSheet("""
                QCheckBox {
                    background-color: transparent;
                    border: 1px solid #777;
                    border-radius: 3px;
                    padding: 10px 15px;
                    color: #f0f0f0;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #FFFFFF; /* MODIFICADO: Borda branca para melhor contraste */
                    border-radius: 3px;
                    background-color: #3e3e3e;
                }
                QCheckBox::indicator:checked {
                     background-color: white; /* MODIFICADO: Cor verde quando marcado */
                     border: 1px solid #FFFFFF;   /* MODIFICADO: Borda verde quando marcado */
                }
            """)
            cb.stateChanged.connect(lambda state, ini=inicio, fim=fim: self.selecionar_faixa(ini, fim, state))
            top_layout.addWidget(cb)
            self.checkbox_faixas[label] = cb

        top_layout.addStretch()
        layout.addLayout(top_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        vbox = QVBoxLayout()
        fonte_cb = QFont("Arial", 11)

        for label, ip in self.lista_pdvs:
            cb = CheckBoxPDV(label, ip)
            cb.setFont(fonte_cb)
            # Esses QCheckBoxes da lista continuam com borda, conforme a sugestão
            cb.setStyleSheet("background-color: transparent; border: 1px solid #777;") # Isso será sobrescrito pelo atualizar_estilo
            self.checkboxes.append(cb)
            vbox.addWidget(cb)

        widget.setLayout(vbox)
        scroll.setWidget(widget)
        layout.addWidget(scroll)

        btn_abrir = QPushButton("Abrir no Navegador")
        btn_abrir.clicked.connect(self.abrir_selecionados)
        layout.addWidget(btn_abrir)

        self.setLayout(layout)

    def selecionar_todos(self, state):
        check = (state == Qt.Checked)
        for cb in self.checkboxes:
            cb.setChecked(check)

    def selecionar_faixa(self, inicio, fim, state):
        check = (state == Qt.Checked)
        for cb in self.checkboxes:
            try:
                if "TERMINAL" in cb.text():
                    num_text = cb.text().replace("TERMINAL", "").strip().split(" ")[0]
                    num = int(num_text) if num_text.isdigit() else 999
                else:
                    num = int(cb.text().split("PDV ")[1].split(" ")[0])

                if inicio <= num <= fim:
                    cb.setChecked(check)
            except (IndexError, ValueError):
                continue

    def abrir_selecionados(self):
        selecionados = [cb.ip for cb in self.checkboxes if cb.isChecked()]
        if not selecionados:
            QMessageBox.warning(self, "Aviso", "Selecione ao menos um PDV.")
            return

        print(f"DEBUG: Tentando abrir {len(selecionados)} PDVs no navegador...") # Log de depuração
        primeiro = True
        for ip in selecionados:
            url = f"http://{ip}:9898/normal.html"
            try:
                if primeiro: webbrowser.open_new(url); primeiro = False
                else: webbrowser.open(url)
                print(f"DEBUG: Tentou abrir {url}") # Log de depuração
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao tentar abrir {url} no navegador:\n{str(e)}")
                print(f"DEBUG: Erro ao abrir {url}: {e}") # Log de depuração
        self.accept()
        self.main_window_ref.activateWindow()
        self.main_window_ref.raise_()

# ========== JANELA DE LOADING ==========
class LoadingDialog(QDialog):
    def __init__(self, message="Aguarde...", parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Carregando...")
        self.setModal(True) # Torna a janela modal para bloquear interação com a principal
        # AJUSTADO: Fundo agora na cor do tema escuro
        self.setStyleSheet("background-color: #3e3e3e; border-radius: 10px;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Container para a animação (GIF ou ProgressBar)
        self.animation_widget = QWidget()
        animation_layout = QVBoxLayout(self.animation_widget)
        animation_layout.setAlignment(Qt.AlignCenter)
        animation_layout.setContentsMargins(0,0,0,0) # Remove margens internas

        gif_path = "loading.gif"
        self.use_progressbar = True # MODIFIED: Always start with progress bar, unless GIF is explicitly loaded.

        if os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            if self.movie.isValid():
                self.gif_label = QLabel()
                self.movie.setCacheMode(QMovie.CacheAll)
                self.movie.setSpeed(100) # Ajuste a velocidade do GIF (100 = normal)
                self.gif_label.setMovie(self.movie)
                animation_layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)
                self.movie.start()
                self.use_progressbar = False # Only if GIF is valid, disable progress bar.
            else:
                print(f"DEBUG: GIF file {gif_path} is invalid. Falling back to progress bar.")
        else:
            print(f"DEBUG: GIF file {gif_path} not found. Falling back to progress bar.")


        if self.use_progressbar:
            self.progress_bar = QProgressBar(self)
            self.progress_bar.setRange(0, 0) # Modo indeterminado
            self.progress_bar.setTextVisible(False) # Esconde a porcentagem de texto
            self.progress_bar.setMinimumSize(200, 20) # Tamanho razoável para a barra
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid #555;
                    border-radius: 10px; /* Metade da altura (20/2) para cantos totalmente arredondados */
                    background-color: #3e3e3e;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #0078d7; /* Cor azul para a animação */
                    border-radius: 9px; /* Levemente menor que o pai para um efeito visual */
                }
            """)
            animation_layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)
            if not self.use_progressbar and self.movie.isValid(): # If gif exists and is valid, hide progress bar
                 self.progress_bar.hide()


        layout.addWidget(self.animation_widget) # Adiciona o container da animação ao layout principal

        self.message_label = QLabel(message)
        self.message_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.message_label.setStyleSheet("color: white; background-color: transparent;")
        layout.addWidget(self.message_label, alignment=Qt.AlignCenter)

        self.adjustSize()
        self.center_on_parent(parent)

    def center_on_parent(self, parent):
        if parent:
            parent_rect = parent.geometry()
            self_rect = self.geometry()
            self.move(parent_rect.x() + (parent_rect.width() - self_rect.width()) // 2,
                      parent_rect.y() + (parent_rect.height() - self_rect.height()) // 2)

    def closeEvent(self, event):
        # Para o movie se ele foi de fato iniciado
        if hasattr(self, 'movie') and self.movie.isValid() and self.movie.state() == QMovie.Running:
            self.movie.stop()
        # Não há necessidade de parar explicitamente QProgressBar em modo indeterminado, mas pode escondê-lo
        if hasattr(self, 'progress_bar'):
            self.progress_bar.hide()
        super().closeEvent(event)

# ========== JANELA DE COMANDOS INDIVIDUAIS ==========
class CommandDialog(QDialog):
    def __init__(self, ip, usuario, senha, pdv_num, main_window_ref, view_mode="Abas"):
        super().__init__(None, Qt.Window) # No parent para que possa ser uma janela independente
        self.setWindowTitle(f"Tela de comandos")
        self.resize(400, 380) # Ajustado o tamanho para acomodar os novos botões
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(main_window_ref.styleSheet()) # Herda o estilo da janela principal
        self.ip = ip
        self.usuario = usuario
        self.senha = senha
        self.pdv_num = pdv_num
        self.main_window_ref = main_window_ref
        self.view_mode = view_mode

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label_info = QLabel(f"PDV {pdv_num}")
        label_info.setFont(QFont("Arial", 14, QFont.Bold))
        label_info.setAlignment(Qt.AlignCenter)
        label_info.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_info)

        # Seção de Comandos Básicos
        label_comandos_basicos = QLabel("Comandos Básicos:")
        label_comandos_basicos.setFont(QFont("Arial", 12, QFont.Bold))
        label_comandos_basicos.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_comandos_basicos)

        btn_restart_app = QPushButton("Reiniciar modo gráfico 🌀")
        btn_restart_app.setMinimumHeight(60)
        btn_restart_app.setFont(FONTE_BOTOES)
        btn_restart_app.clicked.connect(lambda: self.main_window_ref.executar_e_notificar(self.ip, self.usuario, self.senha, "restart-application.sh", "reiniciar-aplicacao", self.pdv_num, self))
        layout.addWidget(btn_restart_app)

        btn_restart_pdv = QPushButton("Reiniciar Máquina 🔄") # Alterado texto
        btn_restart_pdv.setMinimumHeight(60)
        btn_restart_pdv.setFont(FONTE_BOTOES)
        btn_restart_pdv.clicked.connect(lambda: self.main_window_ref.executar_e_notificar(self.ip, self.usuario, self.senha, "init 6", "reiniciar", self.pdv_num, self))
        layout.addWidget(btn_restart_pdv)

        btn_shutdown_pdv = QPushButton("Desligar Máquina 🛑") # Alterado texto
        btn_shutdown_pdv.setMinimumHeight(60)
        btn_shutdown_pdv.setFont(FONTE_BOTOES)
        btn_shutdown_pdv.clicked.connect(lambda: self.main_window_ref.executar_e_notificar(self.ip, self.usuario, self.senha, "init 0", "desligar", self.pdv_num, self))
        layout.addWidget(btn_shutdown_pdv)

        # Adiciona um espaçador entre as seções
        layout.addSpacing(20)

        # Seção de Acesso Remoto
        label_acesso_remoto = QLabel("Acesso Remoto:")
        label_acesso_remoto.setFont(QFont("Arial", 12, QFont.Bold))
        label_acesso_remoto.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_acesso_remoto)

        btn_vnc = QPushButton("Abrir VNC 🖥️")
        btn_vnc.setMinimumHeight(60)
        btn_vnc.setFont(FONTE_BOTOES)
        btn_vnc.clicked.connect(lambda: self.main_window_ref.executar_e_notificar(self.ip, self.usuario, self.senha, None, "vnc", self.pdv_num, self))
        layout.addWidget(btn_vnc)

        btn_putty = QPushButton("Abrir Terminal (Putty/SSH) 💻")
        btn_putty.setMinimumHeight(60)
        btn_putty.setFont(FONTE_BOTOES)
        btn_putty.clicked.connect(lambda: self.main_window_ref.abrir_putty(self.ip, self.usuario))
        layout.addWidget(btn_putty)

        # NOVO: Botão Abrir no Navegador
        btn_open_browser = QPushButton("Abrir no Navegador 🌐")
        btn_open_browser.setMinimumHeight(60)
        btn_open_browser.setFont(FONTE_BOTOES)
        btn_open_browser.clicked.connect(lambda: self.main_window_ref.abrir_tela_pdv(self.ip))
        layout.addWidget(btn_open_browser)

        self.setLayout(layout)
        self.main_window_ref.open_dialogs.append(self) # Keep track of open dialogs for styling updates


# ========== JANELA DE OPÇÕES DE ACESSO GERAL ==========
class GeneralAccessOptionsDialog(QDialog):
    def __init__(self, main_window_ref):
        super().__init__(main_window_ref, Qt.Window)
        self.setWindowTitle("Opções de Acesso Geral")
        self.resize(300, 150)
        self.setStyleSheet(main_window_ref.styleSheet())
        self.main_window_ref = main_window_ref

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        btn_browser_access = QPushButton("Acesso No Navegador 🌐")
        btn_browser_access.setMinimumHeight(40)
        btn_browser_access.setFont(FONTE_BOTOES)
        btn_browser_access.clicked.connect(self.open_browser_access)
        layout.addWidget(btn_browser_access)

        btn_commands_access = QPushButton("Comandos 👨‍💻")
        btn_commands_access.setMinimumHeight(40)
        btn_commands_access.setFont(FONTE_BOTOES)
        btn_commands_access.clicked.connect(self.open_commands_access)
        layout.addWidget(btn_commands_access)

        self.setLayout(layout)

    def open_browser_access(self):
        self.accept() # Fech this diálogo
        self.main_window_ref.abrir_selecao_pdvs_original() # Chaa a função original de acesso via navegador

    def open_commands_access(self):
        self.accept() # Fech this diálogo
        self.main_window_ref.open_all_pdvs_commands_dialog() # Chaa a nova função para comandos em massa

# ========== NEW: Worker class for running commands in parallel ==========
class CommandExecutorWorker(QObject):
    results_ready = pyqtSignal(list, str) # Emits list of results and action description

    def __init__(self, command, action_description, selected_checkboxes):
        super().__init__()
        self._command = command
        self._action_description = action_description
        self._selected_checkboxes = selected_checkboxes

    def run(self):
        results = []
        max_workers = 10

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pdv = {
                executor.submit(self._execute_single_pdv_command, cb, self._command): cb
                for cb in self._selected_checkboxes
            }
            for future in concurrent.futures.as_completed(future_to_pdv):
                cb = future_to_pdv[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    pdv_label = cb.text().replace(" 🖥️", "").strip().replace(" (Offline)", "")
                    results.append(f"{pdv_label} ({cb.ip}): ERRO - {exc}")
        
        self.results_ready.emit(results, self._action_description)

    def _execute_single_pdv_command(self, cb, command):
        ip = cb.ip
        pdv_label = cb.text().replace(" 🖥️", "").strip().replace(" (Offline)", "")
        try:
            senha, _ = gerar_senha(ip)
            result = executar_comando(ip, USUARIO_PADRAO, senha, command)
            return f"{pdv_label} ({ip}): OK - {result.strip() if result.strip() else 'Comando executado.'} ✅"
        except Exception as e:
            return f"{pdv_label} ({ip}): ERRO - {str(e)} ❌"

# ========== JANELA DE COMANDOS PARA TODOS OS PDVs (AGORA COM SELEÇÃO E PARALELIZAÇÃO) ==========
class AllPDVsCommandsDialog(QDialog):
    def __init__(self, main_window_ref, all_pdvs_data):
        super().__init__(main_window_ref, Qt.Window)
        self.setWindowTitle("Comandos para PDVs Selecionados")
        self.resize(500, 600)
        self.setStyleSheet(main_window_ref.styleSheet())
        self.main_window_ref = main_window_ref
        self.all_pdvs_data = all_pdvs_data
        self.checkboxes = []
        self.loading_dialog = None
        self._thread = None # Keep a reference to the thread

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label_info = QLabel("Selecione os PDVs e um comando para executar:")
        label_info.setFont(QFont("Arial", 12, QFont.Bold))
        label_info.setAlignment(Qt.AlignCenter)
        label_info.setStyleSheet("background-color: transparent;")
        layout.addWidget(label_info)

        selection_layout = QHBoxLayout()
        
        self.checkbox_todos = QCheckBox("Selecionar Todos")
        # ESTILO DO CHECKBOX TODOS AJUSTADO AQUI TAMBÉM
        self.checkbox_todos.setStyleSheet("""
            QCheckBox {
                background-color: transparent;
                border: 1px solid #777;
                border-radius: 3px;
                padding: 10px 15px;
                color: #f0f0f0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #FFFFFF; /* MODIFICADO: Borda branca para melhor contraste */
                border-radius: 3px;
                background-color: #3e3e3e;
            }
            QCheckBox::indicator:checked {
                background-color: white; 
                border: 1px solid white;   
            }
        """)
        self.checkbox_todos.stateChanged.connect(self.selecionar_todos)
        selection_layout.addWidget(self.checkbox_todos)
        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        pdv_list_widget = QWidget()
        pdv_list_layout = QVBoxLayout(pdv_list_widget)
        pdv_list_layout.setContentsMargins(0,0,0,0)
        pdv_list_layout.setSpacing(5)
        
        fonte_cb = QFont("Arial", 11)

        for pdv_button, ip in self.all_pdvs_data:
            cb = CheckBoxPDV(pdv_button.text(), ip)
            cb.setFont(fonte_cb)
            cb.setStyleSheet("background-color: transparent;")
            if pdv_button.offline:
                cb.setEnabled(False)
                cb.setText(f"{cb.text()} (Offline)")
                cb.setStyleSheet("color: #777; background-color: transparent;")
            else:
                cb.setChecked(True)
            self.checkboxes.append(cb)
            pdv_list_layout.addWidget(cb)
        
        pdv_list_layout.addStretch()
        scroll_area.setWidget(pdv_list_widget)
        layout.addWidget(scroll_area)

        btn_restart_app = QPushButton("Reiniciar modo gráfico 🌀")
        btn_restart_app.setMinimumHeight(50)
        btn_restart_app.setFont(FONTE_BOTOES)
        btn_restart_app.clicked.connect(lambda: self.confirm_and_execute_selected("restart-application.sh", "reiniciar o modo gráfico"))
        layout.addWidget(btn_restart_app)

        btn_restart_pdvs = QPushButton("Reiniciar PDVs 🔄")
        btn_restart_pdvs.setMinimumHeight(50)
        btn_restart_pdvs.setFont(FONTE_BOTOES)
        btn_restart_pdvs.clicked.connect(lambda: self.confirm_and_execute_selected("init 6", "reiniciar os PDVs"))
        layout.addWidget(btn_restart_pdvs)

        # BOTÃO ATUALIZADO COM O COMANDO CORRETO DE REINICIALIZAÇÃO
        btn_update_pdv = QPushButton("Atualizar e Reiniciar PDVs ⬆️🔄")
        btn_update_pdv.setMinimumHeight(50)
        btn_update_pdv.setFont(FONTE_BOTOES)
        # O comando agora atualiza E agenda a reinicialização de forma desacoplada
        comando_completo = "update-pdv-app && (sleep 3; sudo reboot) &"
        btn_update_pdv.clicked.connect(lambda: self.confirm_and_execute_selected(comando_completo, "Atualizar e Reiniciar PDVs"))
        layout.addWidget(btn_update_pdv)

        self.setLayout(layout)
        self.main_window_ref.atualizar_estilo()


    def selecionar_todos(self, state):
        check = (state == Qt.Checked)
        for cb in self.checkboxes:
            if cb.isEnabled():
                cb.setChecked(check)

    def confirm_and_execute_selected(self, command, action_description):
        selected_pdvs = [cb for cb in self.checkboxes if cb.isChecked() and cb.isEnabled()]
        if not selected_pdvs:
            QMessageBox.warning(self, "Aviso", "Selecione ao menos um PDV online para executar o comando.")
            return

        print("DEBUG: Showing confirmation dialog for mass command...")
        confirm_html = f"""
            <h2 style='color: orange; font-size: 20px;'>⚠️ Comando de Alto Impacto ⚠️</h2>
            <p style='font-size: 16px;'>Você está prestes a <b style='color: yellow;'>{action_description.upper()}</b> em <b style='color: yellow;'>{len(selected_pdvs)} PDV(s) selecionado(s)</b>.</p>
            <p style='font-size: 14px;'>Esta ação <b style='color: red;'>não pode ser desfeita</b> e afetará as operações nos PDVs selecionados.</p>
            <p style='font-size: 18px; font-weight: bold; color: red;'>TEM CERTEZA QUE DESEJA CONTINUAR?</p>
        """

        reply = QMessageBox.question(self,
                                     "ATENÇÃO: EXECUÇÃO DE COMANDO",
                                     confirm_html,
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No
                                    )
        print(f"DEBUG: Confirmation dialog returned: {reply}")
        
        if reply == QMessageBox.Yes:
            self.loading_dialog = LoadingDialog(f"Executando '{action_description}' em {len(selected_pdvs)} PDV(s)...", parent=self)
            
            # Create worker and thread
            self._thread = QThread()
            self._worker = CommandExecutorWorker(command, action_description, selected_pdvs)
            self._worker.moveToThread(self._thread)

            # Connect signals
            self._thread.started.connect(self._worker.run)
            self._worker.results_ready.connect(self._display_results_dialog)
            self._worker.results_ready.connect(self._thread.quit) # Stop the thread when worker is done
            self._thread.finished.connect(self._thread.deleteLater) # Clean up thread

            # Start the thread and show the modal loading dialog
            self._thread.start()
            self.loading_dialog.exec_() # This will block until loading_dialog is closed by _display_results_dialog

    def _display_results_dialog(self, results, action_description):
        # Close loading dialog first
        if self.loading_dialog and self.loading_dialog.isVisible():
            self.loading_dialog.close()
            self.loading_dialog = None

        results_dialog = QDialog(self)
        results_dialog.setWindowTitle(f"Resultados de '{action_description}'")
        results_dialog.resize(600, 400)
        results_dialog.setStyleSheet(self.styleSheet())

        results_layout = QVBoxLayout()
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setFont(QFont("Arial", 10))
        text_area.setText("\n".join(results))
        text_area.setStyleSheet("background-color: #3e3e3e; color: #f0f0f0; border: 1px solid #555;")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(text_area)
        
        results_layout.addWidget(scroll_area)
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(results_dialog.accept)
        results_layout.addWidget(btn_ok)
        results_dialog.setLayout(results_layout)
        results_dialog.exec_()

# ========== JANELA PRINCIPAL ==========
class PDVManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador de PDVs")
        self.setGeometry(200, 100, 1000, 600)
        self.escuro = True
        self.layout = QVBoxLayout()

        self.titulo = QLabel("Gerenciador de PDVs")
        self.titulo.setFont(QFont("Arial", 18, QFont.Bold))
        self.titulo.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.titulo)

        self.subtitulo = QLabel("Mix Russas 518")
        self.subtitulo.setFont(QFont("Arial", 13, QFont.Bold))
        self.subtitulo.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.subtitulo)

       # Layout para os botões do topo
        top_controls_layout = QHBoxLayout()
        top_controls_layout.addStretch() # Mantém os botões à direita

        # O botão de atualizar continua existindo
        self.atualizar_btn = QPushButton("Atualizar 🔄")
        self.atualizar_btn.setFixedWidth(150)
        top_controls_layout.addWidget(self.atualizar_btn)
        
        self.layout.addLayout(top_controls_layout)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.status_label.setFixedHeight(30)
        self.layout.addWidget(self.status_label)

        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        self.layout.addLayout(self.grid)

        self.contador_label = QLabel("")
        self.contador_label.setAlignment(Qt.AlignCenter)
        self.contador_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.layout.addWidget(self.contador_label)

        acesso_layout = QHBoxLayout()
        acesso_layout.addStretch()
        self.btn_acesso_geral = QPushButton("Acesso Geral")
        self.btn_acesso_geral.setFixedSize(150, 40)
        self.btn_acesso_geral.clicked.connect(self.abrir_selecao_pdvs)
        acesso_layout.addWidget(self.btn_acesso_geral)
        self.layout.addLayout(acesso_layout)

        self.setLayout(self.layout)

        self.botoes_pdvs = []
        self.pdv_grid_map = []
        self.open_dialogs = []

        self.comms = Communicate()
        self.comms.update_status.connect(self.on_update_status)
        self.comms.update_message.connect(self.status_label.setText)
        self.comms.show_info_box.connect(self.display_info_box)
        self.comms.show_error_box.connect(self.display_error_box)

        self.atualizar_estilo()
        self.atualizar_btn.clicked.connect(self.atualizar_status_pdvs)

        self.criar_botoes_pdvs()
        self.timer = QTimer()
        self.timer.timeout.connect(self.atualizar_status_pdvs)
        self.timer.start(60000)

    def display_info_box(self, title, message, parent_widget=None):
        QMessageBox.information(parent_widget, title, message)

    def display_error_box(self, title, message, parent_widget=None):
        QMessageBox.critical(parent_widget, title, message)

    def on_update_status(self, status_list, online_count, offline_count):
        for btn, is_offline in status_list:
            btn.set_offline(is_offline)
        self.contador_label.setText(f"Online: {online_count} | Offline: {offline_count}")


    def atualizar_estilo(self):
        if self.escuro:
            checkbox_border_color = "#777"
            checkbox_text_color = "#f0f0f0"
            combobox_arrow_image = "url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmxhdHQAAAAAAAADg+nK7AAABVUlVQ4y2NgoBAwMjAwYDAzMJAAhZmYMDUwcWz/z0AFz//9/P//fwZGDkZmFgb2/7+P/38/MTAwMKCjopKhgUFNQ0NDExMTZgYGCmYmJiYGxvp/r2BgYGT+/v8ZGBiYGNgYGRiA9y4mJgakf//M+P///zMwMDBM/f//PwMDA6Jp/38/MDAwMBqZmJgYGJgZGIYy+v9n+v+f4f9f2///G3///2f/f2D//42BgaHRBwcH//8AAEY2yG8mN+LdAAAAAElFTkSuQmCC)"
            self.setStyleSheet(f"""
                QWidget {{ background-color: #2e2e2e; color: #f0f0f0; }}
                QLabel {{ color: #f0f0f0; background-color: transparent; }}
                QPushButton {{
                    background-color: #444;
                    color: white;
                    font-size: 16px;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 8px;
                }}
                QPushButton:hover {{ background-color: #666; }}
                QDialog {{ background-color: #3e3e3e; color: #f0f0f0; }}
                QLineEdit {{ background-color: #555; color: white; border: 1px solid #777; padding: 5px; }}
                QCheckBox {{
                    color: {checkbox_text_color};
                    background-color: transparent;
                }}
                QScrollArea {{ background-color: #3e3e3e; border: 1px solid #555; }}
                
                QComboBox {{
                    background-color: #555;
                    color: white;
                    border: 1px solid #777;
                    border-radius: 4px;
                    padding-left: 10px;
                    padding-right: 10px;
                    text-align: center;
                }}
                QComboBox::drop-down {{
                    border: 0px;
                }}
                QComboBox::down-arrow {{
                    image: {combobox_arrow_image};
                    width: 16px;
                    height: 16px;
                    margin-right: 5px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: #444;
                    color: white;
                    selection-background-color: #666;
                    text-align: center;
                    padding-left: 10px;
                    padding-right: 10px;
                }}

                QTabWidget::pane {{
                    border-top: 2px solid #555;
                    border-left: 2px solid #555;
                    border-right: 2px solid #555;
                    background-color: #3e3e3e;
                    border-radius: 8px;
                }}
                QTabWidget::tab-bar {{ left: 5px; }}
                QTabBar::tab {{
                    background: #555; border: 1px solid #777; border-bottom-color: #3e3e3e;
                    border-top-left-radius: 4px; border-top-right-radius: 4px;
                    min-width: 100px; padding: 8px; color: white; font-size: 14px;
                }}
                QTabBar::tab:selected {{ background: #3e3e3e; border-color: #555; border-bottom-color: #3e3e3e; }}
                QTabBar::tab:hover:!selected {{ background: #666; }}
                QTextEdit {{ background-color: #3e3e3e; color: #f0f0f0; border: 1px solid #555; padding: 5px; }}
            """)
        else:
            checkbox_border_color = "#ccc"
            checkbox_text_color = "#222"
            combobox_arrow_image = "url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmxhdHQAAAAAAAADg+nK7AAAAq0lVQ4y2NgoGPxgQzMDoxqGGQxGAgyMDMzMDAy/P2P/f0fJwsDAwMDAwMD4g4GBgYX/P/3/j4GBgZGBkYGBAQsDAwOjn////7/AwMDGgYGBAQMDAwMGBoYA96cGBgY/f//fwMDAwMH///8MDAwMjFf///+f///8MDAwMf2BgoGFgYGRiZmBgYGBgZGIYsDAwMPz/j4GBgQULCwsDAwMjAwMjAwMjAwMjAwMjAwMghgYAAJ7nI8xT6Q3fAAAAAElFTkSuQmCC)"
            self.setStyleSheet(f"""
                QWidget {{ background-color: #f0f0f0; color: #222; }}
                QLabel {{ color: #222; background-color: transparent; }}
                QPushButton {{
                    background-color: #ddd; color: black; font-size: 16px;
                    border: 1px solid #ccc; border-radius: 4px; padding: 8px;
                }}
                QPushButton:hover {{ background-color: #bbb; }}
                QDialog {{ background-color: #f9f9f9; color: #222; }}
                QLineEdit {{ background-color: #fff; color: black; border: 1px solid #ccc; padding: 5px; }}
                QCheckBox {{ color: {checkbox_text_color}; background-color: transparent; }}
                QScrollArea {{ background-color: #e0e0e0; border: 1px solid #bbb; }}

                QComboBox {{
                    background-color: #fff; color: black; border: 1px solid #ccc;
                    border-radius: 4px; padding-left: 10px; padding-right: 10px; text-align: center;
                }}
                QComboBox::drop-down {{ border: 0px; }}
                QComboBox::down-arrow {{ image: {combobox_arrow_image}; width: 16px; height: 16px; margin-right: 5px; }}
                QComboBox QAbstractItemView {{
                    background-color: #f0f0f0; color: black; selection-background-color: #bbb;
                    text-align: center; padding-left: 10px; padding-right: 10px;
                }}

                QTabWidget::pane {{
                    border-top: 2px solid #bbb; border-left: 2px solid #bbb; border-right: 2px solid #bbb;
                    background-color: #f9f9f9; border-radius: 8px;
                }}
                QTabWidget::tab-bar {{ left: 5px; }}
                QTabBar::tab {{
                    background: #eee; border: 1px solid #ccc; border-bottom-color: #f9f9f9;
                    border-top-left-radius: 4px; border-top-right-radius: 4px;
                    min-width: 100px; padding: 8px; color: black; font-size: 14px;
                }}
                QTabBar::tab:selected {{ background: #f9f9f9; border-color: #bbb; border-bottom-color: #f9f9f9; }}
                QTabBar::tab:hover:!selected {{ background: #ccc; }}
                QTextEdit {{ background-color: #fff; color: #222; border: 1px solid #ccc; padding: 5px; }}
            """)
        
        self.open_dialogs = [dlg for dlg in self.open_dialogs if dlg and dlg.isVisible()]
        for dlg in self.open_dialogs:
            dlg.setStyleSheet(self.styleSheet())
            palette = QApplication.instance().palette()
            dlg.setPalette(palette)


 
    def atualizar_status_pdvs(self):
        self.comms.update_message.emit("Verificando PDVs, aguarde... 🔄")
        def check_and_update():
            on_count, off_count, status_list = 0, 0, []
            for btn, ip in self.botoes_pdvs:
                if ip:
                    online = is_pdv_online(ip)
                    status_list.append((btn, not online))
                    if online: on_count += 1
                    else: off_count += 1
                else:
                    status_list.append((btn, False))
            self.comms.update_status.emit(status_list, on_count, off_count)
            self.comms.update_message.emit("Verificação concluída. ✅")
        threading.Thread(target=check_and_update, daemon=True).start()

    def criar_botoes_pdvs(self):
        row, col = 0, 0
        self.botoes_pdvs.clear()
        self.pdv_grid_map.clear()
        self.pdv_grid_map.append([])

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        special_buttons_data = [
            ("TERMINAL 100 🖥️", "172.23.128.100", self.conectar),
        ]

        for label, ip, connection_func in special_buttons_data:
            btn = PDVButton(label, ip)
            if ip:
                btn.clicked.connect(lambda _, ip_val=ip: connection_func(ip_val))
            else:
                btn.clicked.connect(connection_func)

            self.grid.addWidget(btn, row, col)
            self.botoes_pdvs.append((btn, ip))
            self.pdv_grid_map[row].append(btn)
            col += 1
            if col >= 6:
                row += 1
                col = 0
                self.pdv_grid_map.append([])

        for i in range(IP_INICIAL, IP_FINAL + 1):
            if i in EXCLUIR_PDVS:
                continue
            ip = BASE_IP + str(i)
            btn = PDVButton(f"PDV {(i - 100):02} 🖥️", ip)
            btn.clicked.connect(lambda _, ip_val=ip: self.conectar(ip_val))
            self.grid.addWidget(btn, row, col)
            self.botoes_pdvs.append((btn, ip))
            self.pdv_grid_map[row].append(btn)
            col += 1
            if col >= 6:
                row += 1
                col = 0
                self.pdv_grid_map.append([])

        if self.pdv_grid_map and not self.pdv_grid_map[-1]:
            self.pdv_grid_map.pop()

        self.atualizar_status_pdvs()

    def conectar(self, ip):
        print(f"DEBUG: PDVManager.conectar called for IP: {ip}")
        senha, pdv_num = gerar_senha(ip)
        login = LoginDialog(ip, pdv_num, self)
        print(f"DEBUG: LoginDialog instance created for IP: {ip}")
        if login.exec_() == QDialog.Accepted:
            print(f"DEBUG: LoginDialog for {ip} returned Accepted.")
            pass
        else:
            print(f"DEBUG: LoginDialog for {ip} returned not Accepted (closed or rejected).")

    def abrir_comandos(self, ip, usuario, senha, pdv_num, view_mode):
        dialog = CommandDialog(ip, usuario, senha, pdv_num, self)
        dialog.show()
        dialog.activateWindow()
        dialog.raise_()
        self.open_dialogs.append(dialog)

    def abrir_selecao_pdvs_original(self):
        lista = []
        for i in range(IP_INICIAL, IP_FINAL + 1):
            ip = BASE_IP + str(i)
            if i in EXCLUIR_PDVS:
                 continue
            label = f"PDV {(i - 100):02} 🖥️"
            lista.append((label, ip))

        dialog = SelecionarPDVsDialog(lista, self)
        dialog.show()
        dialog.activateWindow()
        dialog.raise_()
        self.open_dialogs.append(dialog)

    def abrir_selecao_pdvs(self):
        options_dialog = GeneralAccessOptionsDialog(self)
        options_dialog.exec_()

    def open_all_pdvs_commands_dialog(self):
        filtered_pdvs_data = [
            (btn, ip) for btn, ip in self.botoes_pdvs
            if ip and ip != "172.23.128.100"
        ]
        dialog = AllPDVsCommandsDialog(self, filtered_pdvs_data)
        dialog.exec_()

    def abrir_maxipos_backoffice(self):
        url = "http://pdv.mateus/maxipos_backoffice/app"
        try:
            webbrowser.open_new(url)
            print(f"DEBUG: Abriu MaxiPos Backoffice: {url}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o MaxiPos Backoffice no navegador:\n{str(e)}")
            print(f"DEBUG: Erro ao abrir MaxiPos Backoffice: {e}")

    def abrir_tela_pdv(self, ip):
        url = f"http://{ip}:9898/normal.html"
        try:
            webbrowser.open_new(url)
        except Exception as e:
            QMessageBox.critical(None, "Erro", f"Erro ao abrir navegador:\n{str(e)}")

    def executar_e_notificar(self, ip, usuario, senha, comando, tipo, pdv_num, parent_widget):
        if tipo in ["reiniciar", "desligar"] or comando == "restart-application.sh":
            confirm_msg = f"Tem certeza que deseja {tipo} o PDV {pdv_num}?" if tipo in ["reiniciar", "desligar"] else "Tem certeza que deseja reiniciar o modo gráfico do PDV?"
            reply = QMessageBox.question(parent_widget, "Confirmação", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return

        loading_dialog = None
        if comando == "restart-application.sh":
            loading_dialog = LoadingDialog(f"Reiniciando modo gráfico do PDV {pdv_num}", parent=parent_widget)
            QTimer.singleShot(100, loading_dialog.show)

        def run_command_in_thread():
            try:
                if tipo == "vnc":
                    abrir_vnc(ip)
                    return
                
                resultado = executar_comando(ip, usuario, senha, comando)

                if loading_dialog:
                    QTimer.singleShot(0, loading_dialog.close)

                if tipo in ["reiniciar", "desligar"]:
                    self.comms.show_info_box.emit("Sucesso", f"Comando de {tipo} enviado para o PDV {pdv_num}.", parent_widget)
                elif comando == "restart-application.sh":
                    self.comms.show_info_box.emit("Sucesso", f"Modo gráfico do PDV {pdv_num} reiniciado com sucesso.", parent_widget)
                else:
                    msg = f"Comando '{comando}' executado com sucesso."
                    if resultado.strip():
                        msg += f"\nSaída: {resultado.strip()}"
                    self.comms.show_info_box.emit(f"Resultado no PDV {pdv_num}", msg, parent_widget)
            except Exception as e:
                if loading_dialog:
                    QTimer.singleShot(0, loading_dialog.close)
                self.comms.show_error_box.emit("Erro de Execução", f"Erro ao executar comando no PDV {pdv_num}: {e}", parent_widget)
        
        threading.Thread(target=run_command_in_thread, daemon=True).start()

    def abrir_putty(self, ip, usuario):
        sistema = platform.system().lower()
        try:
            if sistema == "windows":
                putty_path = shutil.which("putty")
                if putty_path:
                    subprocess.Popen([putty_path, "-ssh", f"{usuario}@{ip}"])
                else:
                    QMessageBox.critical(None, "Erro", "PuTTY não encontrado. Certifique-se de que está instalado e no PATH do sistema.")
            elif sistema == "linux":
                terminais = ["gnome-terminal", "mate-terminal", "xfce4-terminal", "konsole", "xterm"]
                terminal_encontrado = next((t for t in terminais if shutil.which(t)), None)

                if not terminal_encontrado:
                    QMessageBox.critical(None, "Erro", "Nenhum terminal suportado encontrado.")
                    return
                
                comando_map = {
                    "konsole": [terminal_encontrado, "--new-tab", "-e", "ssh", f"{usuario}@{ip}"],
                    "xterm": [terminal_encontrado, "-e", "ssh", f"{usuario}@{ip}"]
                }
                comando = comando_map.get(terminal_encontrado, [terminal_encontrado, "--", "ssh", f"{usuario}@{ip}"])
                subprocess.Popen(comando)
            else:
                QMessageBox.information(None, "Info", "Abrir terminal não suportado nesse sistema operacional.")
        except Exception as e:
            QMessageBox.critical(None, "Erro", f"Erro ao abrir terminal:\n{str(e)}")

    def _get_button_coords(self, button):
        for r_idx, row_buttons in enumerate(self.pdv_grid_map):
            try:
                c_idx = row_buttons.index(button)
                return r_idx, c_idx
            except ValueError:
                continue
        return -1, -1

    def keyPressEvent(self, event):
        focused_widget = QApplication.focusWidget()
        if not isinstance(focused_widget, PDVButton) or not self.pdv_grid_map:
            super().keyPressEvent(event)
            return

        current_row, current_col = self._get_button_coords(focused_widget)
        if current_row == -1:
            super().keyPressEvent(event)
            return
        
        num_rows = len(self.pdv_grid_map)
        key = event.key()

        if key in (Qt.Key_Return, Qt.Key_Enter):
            focused_widget.click()
        elif key == Qt.Key_Left:
            new_col = current_col - 1
            new_row = current_row if new_col >= 0 else (current_row - 1 + num_rows) % num_rows
            new_col = new_col if new_col >= 0 else len(self.pdv_grid_map[new_row]) - 1
        elif key == Qt.Key_Right:
            new_col = current_col + 1
            new_row = current_row if new_col < len(self.pdv_grid_map[current_row]) else (current_row + 1) % num_rows
            new_col = new_col if new_col < len(self.pdv_grid_map[current_row]) else 0
        elif key == Qt.Key_Up:
            new_row = (current_row - 1 + num_rows) % num_rows
            new_col = min(current_col, len(self.pdv_grid_map[new_row]) - 1)
        elif key == Qt.Key_Down:
            new_row = (current_row + 1) % num_rows
            new_col = min(current_col, len(self.pdv_grid_map[new_row]) - 1)
        else:
            super().keyPressEvent(event)
            return
        
        next_button = self.pdv_grid_map[new_row][new_col]
        next_button.setFocus()
        event.accept()

from PyQt5.QtWidgets import QApplication, QWidget


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDVManager()
    window.show()
    sys.exit(app.exec_())