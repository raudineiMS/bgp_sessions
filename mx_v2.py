import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import paramiko
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from fpdf import FPDF
import subprocess

def connect_to_router(host, username, password, ssh_port):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=ssh_port, username=username, password=password)
    return Device(host=host, user=username, passwd=password, port=ssh_port, ssh_private_key_file=None, normalize=True)

def get_bgp_sessions(device, filter_type):
    if not device.connected:
        raise Exception("A conexão com o dispositivo foi encerrada. Reconectando...")
    try:
        bgp_information = device.rpc.get_bgp_neighbor_information({'format': 'json'})
        bgp_peers_info = bgp_information.get('bgp-information', [{}])
        bgp_peers = []
        for info in bgp_peers_info:
            peers = info.get('bgp-peer', [])
            for peer in peers:
                peer_state = peer.get('peer-state', [{}])[0].get('data', '').lower()
                if filter_type == 'all' or \
                   (filter_type == 'established' and peer_state == 'established') or \
                   (filter_type == 'not_established' and peer_state != 'established'):
                    peer_group = peer.get('peer-group', [{}])[0].get('data', '')
                    peer_data = {
                        'peer-address': peer.get('peer-address', [{}])[0].get('data', ''),
                        'peer-as': peer.get('peer-as', [{}])[0].get('data', ''),
                        'peer-state': peer_state,
                        'peer-group': peer_group  # Adicionado nome do grupo BGP
                    }
                    bgp_peers.append(peer_data)
        return bgp_peers
    except Exception as e:
        print(f"Erro ao obter informações BGP: {e}")
        return []

def show_dashboard(bgp_sessions, filter_type):
    dashboard = tk.Toplevel()
    dashboard.title(f"BGP Sessions Dashboard - {filter_type.capitalize()}")
    dashboard.geometry("600x400")

    columns = ('peer-address', 'peer-as', 'peer-state')
    tree = ttk.Treeview(dashboard, columns=columns, show='headings')
    tree.heading('peer-address', text='Peer Address')
    tree.heading('peer-as', text='Peer ASN')
    tree.heading('peer-state', text='State')

    for session in bgp_sessions:
        tree.insert('', tk.END, values=(session['peer-address'], session['peer-as'], session['peer-state'], session['peer-group']))

    tree.pack(expand=True, fill='both')

    def deactivate_selected_session():
        selected_items = tree.selection()
        if selected_items:
            selected_item = selected_items[0]
            session_info = tree.item(selected_item, 'values')
        
            if len(session_info) >= 4:
                peer_address_port = session_info[0]
                # Extrai apenas o endereço IP, descartando a porta
                peer_ip = peer_address_port.split('+')[0]
                peer_group = session_info[3]
            
                if messagebox.askyesno("Confirmar", "Desativar a sessão BGP selecionada?"):
                    try:
                        host = entry_ip.get()
                        username = entry_username.get()
                        password = entry_password.get()
                    
                        # Chama a função de desativação com o endereço IP extraído
                        deactivate_bgp_session(host, username, password, peer_ip, peer_group)
                    
                        messagebox.showinfo("Sucesso", "Sessão BGP desativada com sucesso.")
                    except Exception as e:
                        messagebox.showerror("Erro", f"Não foi possível desativar a sessão BGP: {e}")
            else:
                messagebox.showerror("Erro", "Informações insuficientes para desativar a sessão BGP.")
        else:
            messagebox.showwarning("Seleção necessária", "Por favor, selecione uma sessão BGP para desativar.")

    deactivate_button = ttk.Button(dashboard, text="Desativar Sessão BGP", command=deactivate_selected_session)
    deactivate_button.pack(pady=10)

    def export_to_pdf():
        generate_pdf(bgp_sessions)

    export_button = ttk.Button(dashboard, text="Exportar para PDF", command=export_to_pdf)
    export_button.pack(pady=10)

def generate_pdf(output_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=9)
    pdf.cell(200, 10, txt="BGP Sessions Report", ln=True, align='C')
    pdf.ln(10)
    header = ["Peer Address", "ASN", "State"]
    pdf.set_fill_color(169, 169, 169)
    pdf.set_text_color(0, 0, 0)
    for item in header:
        pdf.cell(60, 10, txt=item, border=1, fill=True)
    pdf.ln()
    for peer in output_data:
        pdf.cell(60, 10, txt=peer['peer-address'], border=1)
        pdf.cell(60, 10, txt=peer['peer-as'], border=1)
        pdf.cell(60, 10, txt=peer['peer-state'], border=1)
        pdf.ln()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pdf_output_filename = f"bgp_sessions_{timestamp}.pdf"
    pdf.output(pdf_output_filename)
    subprocess.Popen(["start", pdf_output_filename], shell=True)
    messagebox.showinfo("Export Successful", f"PDF exported: {pdf_output_filename}")

def deactivate_bgp_session(host, username, password, peer_ip, peer_group):
    try:
        with Device(host=host, user=username, passwd=password) as dev:
            dev.open()
            with Config(dev) as cu:
                # Certifique-se de que o comando corresponde à sua configuração
                set_command = f"deactivate protocols bgp group {peer_group} neighbor {peer_ip}"
                cu.load(set_command, format='set', merge=True)
                if cu.commit_check():
                    cu.commit()
                    print(f"Sessão BGP com {peer_ip} no grupo {peer_group} desativada com sucesso.")
                else:
                    raise Exception("Falha ao validar a configuração antes do commit.")
    except Exception as e:
        print(f"Erro ao desativar sessão BGP: {e}")
        raise  # Re-lança a exceção para ser capturada pelo chamador
    
def execute_script(ip, username, password, port, filter_type):
    router_device = connect_to_router(ip, username, password, port)
    try:
        router_device.open()
        bgp_sessions_list = get_bgp_sessions(router_device, filter_type)
        if bgp_sessions_list:
            show_dashboard(bgp_sessions_list, filter_type)
        else:
            messagebox.showinfo("Information", f"No BGP sessions {filter_type} found.")
    except Exception as e:
        messagebox.showerror("Error", f"Error: {e}")
    finally:
        router_device.close()

def run_script_all():
    run_script(filter_type='all')

def run_script_established():
    run_script(filter_type='established')

def run_script_not_established():
    run_script(filter_type='not_established')

def run_script(filter_type):
    ip = entry_ip.get()
    username = entry_username.get()
    password = entry_password.get()
    port = entry_port.get()

    if not ip or not username or not password or not port:
        messagebox.showwarning("Aviso", "Por favor, preencha todos os campos.")
        return

    execute_script(ip, username, password, port, filter_type)

# Interface Gráfica
root = tk.Tk()
root.title("Sessões BGP - by Raudinei")

style = ttk.Style()
style.theme_use("clam")

root.configure(bg="#2C3E50")
style.configure("TLabel", background="#2C3E50", foreground="#ECF0F1")
style.configure("TButton", background="#3498DB", foreground="#ECF0F1", width=20)
style.configure("TEntry", fieldbackground="#EAECEE", foreground="#2C3E50")

# Configuração do Tamanho da Janela e Posicionamento
window_width = 400
window_height = 200

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

x_coordinate = (screen_width / 2) - (window_width / 2)
y_coordinate = (screen_height / 2) - (window_height / 2)

root.geometry(f"{window_width}x{window_height}+{int(x_coordinate)}+{int(y_coordinate)}")

# Definição dos Widgets
label_ip = ttk.Label(root, text="Endereço IP:")
label_username = ttk.Label(root, text="Usuário:")
label_password = ttk.Label(root, text="Senha:")
label_port = ttk.Label(root, text="Porta:")

entry_ip = ttk.Entry(root)
entry_username = ttk.Entry(root)
entry_password = ttk.Entry(root, show="*")
entry_port = ttk.Entry(root)

button_run_all = ttk.Button(root, text="Todas as sessões", command=run_script_all)
button_run_established = ttk.Button(root, text="Estabelecidas", command=run_script_established)
button_run_not_established = ttk.Button(root, text="Não estabelecidas", command=run_script_not_established)

# Posicionamento dos Widgets usando grid
label_ip.grid(row=0, column=0, padx=10, pady=5, sticky='W')
entry_ip.grid(row=0, column=1, pady=5, sticky='WE')
label_username.grid(row=1, column=0, padx=10, pady=5, sticky='W')
entry_username.grid(row=1, column=1, pady=5, sticky='WE')
label_password.grid(row=2, column=0, padx=10, pady=5, sticky='W')
entry_password.grid(row=2, column=1, pady=5, sticky='WE')
label_port.grid(row=3, column=0, padx=10, pady=5, sticky='W')
entry_port.grid(row=3, column=1, pady=5, sticky='WE')

button_run_all.grid(row=0, column=2, padx=10, pady=5, sticky='WE')
button_run_established.grid(row=1, column=2, padx=10, pady=5, sticky='WE')
button_run_not_established.grid(row=2, column=2, padx=10, pady=5, sticky='WE')

root.grid_columnconfigure(1, weight=1)  # Faz com que a coluna do meio (onde estão os Entry) expanda

root.mainloop()
