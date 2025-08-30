# Arquivo: servidor_mobile.py

from flask import Flask, render_template, jsonify, request
import paramiko
import platform
import subprocess
from datetime import date
import concurrent.futures

# ========== CONFIGURAÇÃO ==========
IP_INICIAL = 101
IP_FINAL = 132
EXCLUIR_PDVS = [131]
BASE_IP = "172.23.101."
USUARIO_PADRAO = "suporte"

app = Flask(__name__)

# ========== FUNÇÕES (sem alterações) ==========
def gerar_senha(ip):
    try:
        ultimo_num = int(ip.split('.')[-1])
        pdv_num = ultimo_num - 100
        label = f"PDV {pdv_num:02}"
        hoje = date.today()
        valor = int(str(hoje.day) + str(hoje.month)) + pdv_num
        senha = f"pdv@{valor}"
        return senha, label, pdv_num
    except (ValueError, IndexError):
        return None, "IP Inválido", None

def executar_comando(ip, usuario, senha, comando):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=usuario, password=senha, timeout=5)
        timeout_exec = 30 if "reboot" in comando or "init" in comando else 10
        comando_sudo = f'echo "{senha}" | sudo -S {comando}'
        stdin, stdout, stderr = ssh.exec_command(comando_sudo, timeout=timeout_exec)
        saida = stdout.read().decode().strip()
        erro = stderr.read().decode().strip()
        ssh.close()
        if "reboot" in comando or "init" in comando:
            return "Comando de reinicialização enviado." if not erro else f"Erro: {erro}"
        return saida if saida and not erro else erro if erro else "Comando executado com sucesso."
    except Exception as e:
        if "reboot" in comando or "init" in comando and isinstance(e, paramiko.ssh_exception.SSHException):
            return "Comando de reinicialização enviado (conexão encerrada como esperado)."
        return f"Erro de conexão: {str(e)}"

def is_pdv_online(ip, timeout=0.5): # Timeout agressivo para respostas rápidas
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    comando = ['ping', param, '1', ip]
    try:
        return subprocess.call(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 1) == 0
    except (subprocess.TimeoutExpired, Exception):
        return False

# ========== ROTAS DO SERVIDOR WEB (OTIMIZADAS) ==========

@app.route('/')
def index():
    """ Rota principal - AGORA CARREGA INSTANTANEAMENTE """
    all_ips = [BASE_IP + str(i) for i in range(IP_INICIAL, IP_FINAL + 1) if i not in EXCLUIR_PDVS]
    pdvs = []
    for ip in all_ips:
        _, label, _ = gerar_senha(ip)
        pdvs.append({"ip": ip, "label": label})
    pdvs.sort(key=lambda x: int(x['ip'].split('.')[-1]))
    return render_template('index.html', pdvs=pdvs)

@app.route('/acesso-geral')
def acesso_geral_page():
    """ Rota Acesso Geral - AGORA CARREGA INSTANTANEAMENTE """
    all_ips = [BASE_IP + str(i) for i in range(IP_INICIAL, IP_FINAL + 1) if i not in EXCLUIR_PDVS]
    pdvs = []
    for ip in all_ips:
        _, label, _ = gerar_senha(ip)
        pdvs.append({"ip": ip, "label": label})
    pdvs.sort(key=lambda x: int(x['ip'].split('.')[-1]))
    return render_template('acesso_geral.html', pdvs=pdvs)

# --- [NOVO] ENDPOINT DE API PARA STATUS ---
@app.route('/api/status/all')
def get_all_pdv_status():
    """ Faz o trabalho lento de pingar e retorna um JSON. """
    all_ips = [BASE_IP + str(i) for i in range(IP_INICIAL, IP_FINAL + 1) if i not in EXCLUIR_PDVS]
    def check_pdv(ip):
        online = is_pdv_online(ip)
        return {"ip": ip, "online": online}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(check_pdv, all_ips))
    return jsonify(results)

# --- ROTAS DE COMANDO (sem alterações) ---
@app.route('/pdv/<string:ip>')
def pdv_comandos_page(ip):
    online = is_pdv_online(ip) # Ping único, a lentidão aqui é aceitável
    senha, label, _ = gerar_senha(ip)
    pdv_info = {"ip": ip, "label": label, "online": online, "senha": senha}
    return render_template('pdv_comandos.html', pdv=pdv_info)

# ... (as rotas /comando/individual e /comando/em-massa continuam exatamente iguais) ...
@app.route('/comando/individual/<string:ip>/<string:acao>', methods=['POST'])
def comando_individual(ip, acao):
    senha, _, _ = gerar_senha(ip)
    comandos_map = {
        'reiniciar_app': "restart-application.sh", 'reiniciar_maquina': "init 6", 'desligar_maquina': "init 0"
    }
    comando_real = comandos_map.get(acao)
    if not comando_real: return jsonify({"sucesso": False, "mensagem": "Ação desconhecida."}), 400
    resultado = executar_comando(ip, USUARIO_PADRAO, senha, comando_real)
    sucesso = "erro" not in resultado.lower()
    return jsonify({"sucesso": sucesso, "mensagem": resultado})

@app.route('/comando/em-massa', methods=['POST'])
def comando_em_massa():
    data = request.get_json()
    ips_selecionados = data.get('ips')
    acao = data.get('acao')
    if not ips_selecionados or not acao: return jsonify({"sucesso": False, "resultados": ["Nenhum PDV ou ação selecionada."]}), 400
    comandos_map = {'reiniciar_app': "restart-application.sh", 'reiniciar_maquina': "init 6"}
    comando_real = comandos_map.get(acao)
    if not comando_real: return jsonify({"sucesso": False, "resultados": [f"Ação '{acao}' é inválida."]}), 400
    def executar_para_um_pdv(ip):
        senha, label, _ = gerar_senha(ip)
        resultado = executar_comando(ip, USUARIO_PADRAO, senha, comando_real)
        return f"{label}: {resultado}"
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        resultados = list(executor.map(executar_para_um_pdv, ips_selecionados))
    return jsonify({"sucesso": True, "resultados": resultados})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context='adhoc')