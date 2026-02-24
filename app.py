from flask import Flask, render_template, request, session, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from collections import Counter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import random
import os
import io

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURAÇÃO DO BANCO DE DADOS (HÍBRIDO) ---
basedir = os.path.abspath(os.path.dirname(__file__))

# Tenta pegar a URL do banco do Render (PostgreSQL)
database_url = os.environ.get('DATABASE_URL')

# Ajuste necessário para o Render (postgres:// -> postgresql://)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Se não tiver URL (estamos no Mac), usa SQLite local
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'mathkids.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CONFIGURAÇÃO DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar essa página."


# --- BANCO DE PROBLEMAS DIVERTIDOS ---
LISTA_PROBLEMAS = [
    {"p": "O Pirata Barba-Ruiva tinha 10 moedas de ouro. Ele achou um baú com mais 5. Quantas moedas ele tem agora?", "r": 15, "op": "+"},
    {"p": "Uma aranha tem 8 pernas. Quantas pernas têm 2 aranhas juntas?", "r": 16, "op": "x"},
    {"p": "O Astronauta levou 12 sanduíches para a Lua. Ele comeu 4 na viagem. Quantos sobraram?", "r": 8, "op": "-"},
    {"p": "A bruxa quer dividir 20 sapos igualmente em 4 caldeirões. Quantos sapos vão em cada caldeirão?", "r": 5, "op": "÷"},
    {"p": "Quanto é: 2 + 2 x 3? (Lembre-se: multiplicação vem primeiro!)", "r": 8, "op": "x"},
    {"p": "O Zumbi perdeu 3 dentes na segunda e 4 na terça. Quantos dentes ele perdeu ao todo?", "r": 7, "op": "+"},
    {"p": "Se 1 gato tem 4 patas, quantas patas têm 5 gatos?", "r": 20, "op": "x"},
    {"p": "Tenho 30 balas e quero dar 5 para cada amigo. Quantos amigos vão ganhar balas?", "r": 6, "op": "÷"},
    {"p": "O Creeper estava no nível 15. Ele caiu 5 níveis. Em que nível ele está?", "r": 10, "op": "-"},
    {"p": "Expressão maluca: 10 - 2 + 5 = ?", "r": 13, "op": "+"},
    {"p": "O Vampiro dorme 10 horas por dia. Quantas horas ele dorme em 3 dias?", "r": 30, "op": "x"},
    {"p": "Havia 12 pedaços de pizza. O cachorro comeu metade. Quantos sobraram?", "r": 6, "op": "÷"}
]

# --- MODELOS (TABELAS) ---

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    operacao = db.Column(db.String(10))
    conta = db.Column(db.String(50))
    resposta_aluno = db.Column(db.Integer)
    resposta_correta = db.Column(db.Integer)
    acertou = db.Column(db.Boolean)
    data = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

# Cria o banco de dados se não existir
with app.app_context():
    db.create_all()

# --- FUNÇÕES AUXILIARES ---

def gerar_4_opcoes(resposta_certa):
    """Gera 4 opções: 1 certa e 3 erradas"""
    opcoes = {resposta_certa}
    while len(opcoes) < 4:
        desvio = random.randint(-10, 10)
        if desvio != 0:
            errada = resposta_certa + desvio
            if errada >= 0: # Evita negativos se a resposta for positiva
                opcoes.add(errada)
    lista = list(opcoes)
    random.shuffle(lista) # Mistura tudo
    return lista

def gerar_opcoes(resposta_certa):
    """Gera 3 opções para o Flashcard (1 certa + 2 erradas)"""
    opcoes = {resposta_certa}
    while len(opcoes) < 3:
        desvio = random.randint(-5, 5)
        if desvio != 0:
            errada = resposta_certa + desvio
            # Nota: Permitimos números negativos nas opções agora
            opcoes.add(errada)
    lista = list(opcoes)
    random.shuffle(lista)
    return lista

def gerar_texto_ajuda(n1, n2, op):
    # Ajuda para Negativos
    if n1 < 0 or n2 < 0:
        if op == 'x' or op == '*':
            return "Regra dos Sinais: Sinais IGUAIS dá POSITIVO (+). Sinais DIFERENTES dá NEGATIVO (-)."
        elif op == '+' or op == '-':
            return "Dica da Dívida: Pense em dinheiro. Negativo é dívida, Positivo é dinheiro no bolso."

    # Ajuda Padrão
    if op == '+': return f"Guarde o número {n1} na cabeça e conte mais {n2} dedos!"
    if op == '-': return f"Coloque {n1} dedos e abaixe {n2}. Quantos sobraram?"
    if op == '*': return f"Isso é o mesmo que somar o número {n1}, {n2} vezes."
    if op == '/': return f"Imagine dividir {n1} balas para {n2} amigos."
    if op == '÷': return f"Imagine dividir {n1} balas para {n2} amigos."
    return "Tente contar devagar!"

def analisar_fraquezas_aluno():
    erros = Historico.query.filter_by(student_id=current_user.id, acertou=False).all()
    if not erros: return None, None

    ops = [e.operacao for e in erros]
    op_mais_errada = Counter(ops).most_common(1)[0][0]
    detalhe = None

    if op_mais_errada == 'x':
        numeros = []
        for e in erros:
            if e.operacao == 'x':
                partes = e.conta.split(' x ')
                try:
                    # Remove parenteses se houver para pegar o numero puro
                    n1 = int(partes[0].replace('(','').replace(')',''))
                    n2 = int(partes[1].replace('(','').replace(')',''))
                    numeros.append(n1)
                    numeros.append(n2)
                except: pass
        if numeros:
            detalhe = Counter(numeros).most_common(1)[0][0]

    return op_mais_errada, detalhe

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form.get('name')
        usuario = request.form.get('username')
        senha = request.form.get('password')

        if Student.query.filter_by(username=usuario).first():
            flash('Este nome de usuário já existe!')
            return redirect(url_for('register'))

        novo_aluno = Student(name=nome, username=usuario)
        novo_aluno.set_password(senha)
        db.session.add(novo_aluno)
        db.session.commit()
        
        login_user(novo_aluno)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('username')
        senha = request.form.get('password')
        aluno = Student.query.filter_by(username=usuario).first()
        
        if aluno and aluno.check_password(senha):
            login_user(aluno)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ROTAS DO JOGO ---

@app.route('/')
@login_required
def index():
    return render_template('menu.html', nome=current_user.name)

# --- MODO CLÁSSICO (DIGITAR) ---

@app.route('/iniciar/<modo>')
@login_required
def iniciar(modo):
    session['modo'] = modo
    session['score'] = 0
    return redirect(url_for('nova_pergunta'))

@app.route('/nova_pergunta')
@login_required
def nova_pergunta():
    op_modo = session.get('modo', 'todas')
    
    # Lógica para Negativos
    if op_modo == 'negativos':
        op = random.choice(['+', '-', '*'])
        faixa = [n for n in range(-9, 10) if n != 0]
        num1 = random.choice(faixa)
        num2 = random.choice(faixa)
        
        if op == '*': resp = num1 * num2
        elif op == '-': resp = num1 - num2
        else: resp = num1 + num2

        session['num1'] = num1
        session['num2'] = num2
        session['operador_visual'] = 'x' if op == '*' else op
        session['resposta_correta'] = resp
        return redirect(url_for('jogo'))

    # Lógica Padrão
    operadores = ['+', '-', '*', '/']
    op = op_modo if op_modo in ['+', '-', '*', '/'] else random.choice(operadores)
    
    num1, num2, resp = 0, 0, 0
    if op == '/':
        divisor = random.randint(2, 9)
        resp = random.randint(2, 9)
        num1 = divisor * resp
        num2 = divisor
    elif op == '*':
        num1 = random.randint(2, 9)
        num2 = random.randint(2, 9)
        resp = num1 * num2
    elif op == '-':
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        if num1 < num2: num1, num2 = num2, num1
        resp = num1 - num2
    else:
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        resp = num1 + num2

    session['num1'] = num1
    session['num2'] = num2
    if op == '/': visual = '÷'
    elif op == '*': visual = 'x'
    else: visual = op
    session['operador_visual'] = visual
    session['resposta_correta'] = resp
    
    return redirect(url_for('jogo'))

@app.route('/jogo', methods=['GET', 'POST'])
@login_required
def jogo():
    if 'num1' not in session:
        return redirect(url_for('nova_pergunta'))

    feedback = None
    cor_feedback = ""
    acertou = False
    mostrar_ajuda = False

    if request.method == 'POST':
        try:
            resp_user = request.form.get('resposta')
            if resp_user:
                resp_user = int(resp_user)
                resp_real = session.get('resposta_correta')
                acertou = (resp_user == resp_real)

                novo = Historico(
                    student_id=current_user.id,
                    operacao=session['operador_visual'],
                    conta=f"{session['num1']} {session['operador_visual']} {session['num2']}",
                    resposta_aluno=resp_user,
                    resposta_correta=resp_real,
                    acertou=acertou
                )
                db.session.add(novo)
                db.session.commit()

                if acertou:
                    session['score'] += 1
                    feedback = "MUITO BEM! 🎉"
                    cor_feedback = "green"
                else:
                    feedback = "Ops! Tente de novo. 👇"
                    cor_feedback = "#D32F2F"
                    mostrar_ajuda = True
        except:
            pass
    
    dica = gerar_texto_ajuda(session['num1'], session['num2'], session['operador_visual'])

    return render_template('jogo.html', 
                           num1=session['num1'], 
                           num2=session['num2'], 
                           operador=session['operador_visual'],
                           score=session['score'],
                           feedback=feedback,
                           cor_feedback=cor_feedback,
                           acertou=acertou,
                           mostrar_ajuda=mostrar_ajuda,
                           dica_texto=dica)

# --- MODO FLASHCARDS ---

@app.route('/iniciar_flashcards/<modo>')
@login_required
def iniciar_flashcards(modo):
    session['modo'] = modo
    session['score'] = 0
    return redirect(url_for('nova_pergunta_flash'))

@app.route('/nova_pergunta_flash')
@login_required
def nova_pergunta_flash():
    op_modo = session.get('modo', 'todas')
    
    # Lógica Negativos Flash
    if op_modo == 'negativos':
        op = random.choice(['+', '-', '*'])
        faixa = [n for n in range(-9, 10) if n != 0]
        num1 = random.choice(faixa)
        num2 = random.choice(faixa)
        
        if op == '*': resp = num1 * num2
        elif op == '-': resp = num1 - num2
        else: resp = num1 + num2

        session['num1'] = num1
        session['num2'] = num2
        session['operador_visual'] = 'x' if op == '*' else op
        session['resposta_correta'] = resp
        session['opcoes_flash'] = gerar_opcoes(resp)
        return redirect(url_for('jogo_flashcards'))

    # Lógica Padrão Flash
    operadores = ['+', '-', '*', '/']
    op = op_modo if op_modo in ['+', '-', '*', '/'] else random.choice(operadores)
    
    num1, num2, resp = 0, 0, 0
    if op == '/':
        divisor = random.randint(2, 9)
        resp = random.randint(2, 9)
        num1 = divisor * resp
        num2 = divisor
    elif op == '*':
        num1 = random.randint(2, 9)
        num2 = random.randint(2, 9)
        resp = num1 * num2
    elif op == '-':
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        if num1 < num2: num1, num2 = num2, num1
        resp = num1 - num2
    else:
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        resp = num1 + num2

    session['num1'] = num1
    session['num2'] = num2
    if op == '/': visual = '÷'
    elif op == '*': visual = 'x'
    else: visual = op
    session['operador_visual'] = visual
    session['resposta_correta'] = resp
    session['opcoes_flash'] = gerar_opcoes(resp)
    
    return redirect(url_for('jogo_flashcards'))

@app.route('/jogo_flashcards', methods=['GET', 'POST'])
@login_required
def jogo_flashcards():
    if 'opcoes_flash' not in session:
        return redirect(url_for('nova_pergunta_flash'))

    feedback = None
    cor_feedback = ""
    acertou = False
    
    if request.method == 'POST':
        try:
            resp_user = int(request.form.get('resposta'))
            resp_real = session.get('resposta_correta')
            acertou = (resp_user == resp_real)

            novo = Historico(
                student_id=current_user.id,
                operacao=session['operador_visual'],
                conta=f"{session['num1']} {session['operador_visual']} {session['num2']}",
                resposta_aluno=resp_user,
                resposta_correta=resp_real,
                acertou=acertou
            )
            db.session.add(novo)
            db.session.commit()

            if acertou:
                session['score'] += 1
                feedback = "ACERTOU! 🌟"
                cor_feedback = "green"
            else:
                feedback = f"Ops! A certa era {resp_real}."
                cor_feedback = "#D32F2F"
        except:
            pass

    return render_template('flashcards.html', 
                           num1=session['num1'], 
                           num2=session['num2'], 
                           operador=session['operador_visual'],
                           score=session['score'],
                           opcoes=session['opcoes_flash'],
                           feedback=feedback,
                           cor_feedback=cor_feedback,
                           acertou=acertou)

# --- RELATÓRIOS E PDF ---

@app.route('/relatorio')
@login_required
def relatorio():
    historico = Historico.query.filter_by(student_id=current_user.id).order_by(Historico.data.desc()).limit(100).all()
    total = Historico.query.filter_by(student_id=current_user.id).count()
    acertos = Historico.query.filter_by(student_id=current_user.id, acertou=True).count()
    erros = total - acertos

    op_fraca, detalhe = analisar_fraquezas_aluno()
    
    msg = "Jogue mais para gerarmos uma análise."
    if op_fraca == 'x' and detalhe: msg = f"Dificuldade: Tabuada do {detalhe}."
    elif op_fraca == '+': msg = "Dificuldade: Adição."
    elif op_fraca == '-': msg = "Dificuldade: Subtração."
    elif op_fraca == '÷': msg = "Dificuldade: Divisão."

    return render_template('relatorio.html', 
                           historico=historico, total=total, 
                           acertos=acertos, erros=erros,
                           mensagem_analise=msg,
                           nome_aluno=current_user.name)

@app.route('/baixar_pdf')
@login_required
def baixar_pdf():
    op_fraca, detalhe = analisar_fraquezas_aluno()
    if not op_fraca: op_fraca = 'mix'

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    c.setFont("Helvetica-Bold", 20)
    c.drawString(100, 800, "Math Kids - Folha de Treino")
    c.setFont("Helvetica", 12)
    c.drawString(100, 780, f"Aluno: {current_user.name}")
    
    titulo_foco = "Treino Geral"
    if op_fraca == 'x': titulo_foco = f"Foco: Tabuada do {detalhe}"
    elif op_fraca == '+': titulo_foco = "Foco: Adição"
    elif op_fraca == '-': titulo_foco = "Foco: Subtração"
    elif op_fraca == '÷': titulo_foco = "Foco: Divisão"
    
    c.drawString(100, 760, titulo_foco)

    y = 720
    c.setFont("Helvetica", 16)
    
    for i in range(1, 21):
        n1, n2, simbolo = 0, 0, ""
        
        if op_fraca == 'x':
            simbolo = 'x'
            if detalhe and random.random() < 0.8:
                n1 = detalhe
                n2 = random.randint(2, 9)
            else:
                n1 = random.randint(2, 9)
                n2 = random.randint(2, 9)
        elif op_fraca == '+':
            simbolo = '+'
            n1 = random.randint(1, 20)
            n2 = random.randint(1, 20)
        elif op_fraca == '-':
            simbolo = '-'
            n1 = random.randint(1, 20)
            n2 = random.randint(1, 20)
            if n1 < n2: n1, n2 = n2, n1
        elif op_fraca == '÷':
            simbolo = '/'
            divisor = random.randint(2, 9)
            resp = random.randint(2, 9)
            n1 = divisor * resp
            n2 = divisor
        else:
            simbolo = random.choice(['+', '-', 'x'])
            n1 = random.randint(2, 10)
            n2 = random.randint(2, 10)
            if simbolo == '-' and n1 < n2: n1, n2 = n2, n1

        c.drawString(100, y, f"{i}.   {n1} {simbolo} {n2} = _____")
        y -= 30

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"exercicios_{current_user.username}.pdf", mimetype='application/pdf')

# --- ROTAS MODO PROBLEMA ---

@app.route('/iniciar_problema')
@login_required
def iniciar_problema():
    session['modo'] = 'problema'
    session['score'] = 0
    return redirect(url_for('nova_pergunta_problema'))

@app.route('/nova_pergunta_problema')
@login_required
def nova_pergunta_problema():
    # Sorteia um problema da lista
    problema = random.choice(LISTA_PROBLEMAS)
    
    session['texto_problema'] = problema['p']
    session['resposta_correta'] = problema['r']
    session['operador_visual'] = problema['op'] # Para salvar no histórico
    
    # Gera as 4 alternativas
    session['opcoes_problema'] = gerar_4_opcoes(problema['r'])
    
    # Salva num1 e num2 como 0 apenas para não quebrar o histórico do banco
    session['num1'] = 0
    session['num2'] = 0
    
    return redirect(url_for('jogo_problema'))

@app.route('/jogo_problema', methods=['GET', 'POST'])
@login_required
def jogo_problema():
    if 'texto_problema' not in session:
        return redirect(url_for('nova_pergunta_problema'))

    feedback = None
    cor_feedback = ""
    acertou = False
    
    if request.method == 'POST':
        try:
            resp_user = int(request.form.get('resposta'))
            resp_real = session.get('resposta_correta')
            acertou = (resp_user == resp_real)

            # Salva no histórico (A conta será o texto resumido ou "Problema")
            novo = Historico(
                student_id=current_user.id,
                operacao='?', # Símbolo de problema
                conta="Desafio Lógico", # Ou session['texto_problema'][:40]...
                resposta_aluno=resp_user,
                resposta_correta=resp_real,
                acertou=acertou
            )
            db.session.add(novo)
            db.session.commit()

            if acertou:
                session['score'] += 1
                feedback = "RACIOCÍNIO BRILHANTE! 🧠"
                cor_feedback = "green"
            else:
                feedback = f"Que pena! A resposta certa era {resp_real}."
                cor_feedback = "#D32F2F"
        except:
            pass

    return render_template('problema.html', 
                           pergunta=session['texto_problema'], 
                           score=session['score'],
                           opcoes=session['opcoes_problema'],
                           feedback=feedback,
                           cor_feedback=cor_feedback,
                           acertou=acertou)

if __name__ == '__main__':
    app.run(debug=True)