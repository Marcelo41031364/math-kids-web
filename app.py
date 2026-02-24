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

# --- CONFIGURAÇÃO DO BANCO ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'mathkids.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- CONFIGURAÇÃO DE LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Se não estiver logado, manda pra cá
login_manager.login_message = "Por favor, insira seu usuário e senha."

# --- MODELOS (TABELAS) ---

# Tabela de Alunos (Usuários)
class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Tabela de Histórico (Agora vinculada ao Aluno)
class Historico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id')) # Vínculo
    operacao = db.Column(db.String(10))
    conta = db.Column(db.String(50))
    resposta_aluno = db.Column(db.Integer)
    resposta_correta = db.Column(db.Integer)
    acertou = db.Column(db.Boolean)
    data = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

# Cria o banco novo
with app.app_context():
    db.create_all()

# --- INTELIGÊNCIA ---
def analisar_fraquezas_aluno():
    # Filtra erros APENAS do aluno logado
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
                    numeros.append(int(partes[0]))
                    numeros.append(int(partes[1]))
                except: pass
        if numeros:
            detalhe = Counter(numeros).most_common(1)[0][0]

    return op_mais_errada, detalhe

# --- FUNÇÃO AUXILIAR PARA FLASHCARDS ---
def gerar_opcoes(resposta_certa):
    """Gera 3 opções: a certa e duas erradas próximas"""
    opcoes = {resposta_certa} # Usa um set para evitar duplicatas
    
    while len(opcoes) < 3:
        # Gera um erro entre -5 e +5 (ex: se a resposta é 20, gera 18, 23, etc)
        desvio = random.randint(-5, 5)
        if desvio != 0:
            errada = resposta_certa + desvio
            # Evita números negativos
            if errada < 0: errada = 0
            opcoes.add(errada)
    
    lista_opcoes = list(opcoes)
    random.shuffle(lista_opcoes) # Embaralha para a certa não ficar sempre no mesmo lugar
    return lista_opcoes

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form.get('name')
        usuario = request.form.get('username')
        senha = request.form.get('password')

        # Verifica se usuário já existe
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
    session['operador_real'] = op
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

                # Salva no Banco VINCULADO AO ALUNO
                novo = Historico(
                    student_id=current_user.id, # <--- AQUI ESTÁ A MÁGICA
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
    
    op = session['operador_visual']
    n1, n2 = session['num1'], session['num2']
    dica = "Tente contar nos dedos!"
    if op == '+': dica = f"Comece do {n1} e conte mais {n2}."
    if op == '-': dica = f"Tenho {n1}, tiro {n2}. Sobra quanto?"
    if op == 'x': dica = f"Some o número {n1}, {n2} vezes."
    if op == '÷': dica = f"Divida {n1} balas para {n2} amigos."

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

@app.route('/relatorio')
@login_required
def relatorio():
    # Filtra apenas o histórico do usuário atual
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
    c.drawString(100, 780, f"Aluno: {current_user.name}") # Nome do aluno no PDF
    
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

# --- ROTAS FLASHCARDS ---

@app.route('/iniciar_flashcards/<modo>')
@login_required
def iniciar_flashcards(modo):
    session['modo'] = modo
    session['score'] = 0
    return redirect(url_for('nova_pergunta_flash'))

@app.route('/nova_pergunta_flash')
@login_required
def nova_pergunta_flash():
    # Reutiliza a lógica de gerar números (copie a lógica da nova_pergunta ou refatore se quiser)
    # Para simplificar, vou repetir a lógica básica aqui:
    op_modo = session.get('modo', 'todas')
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
    
    # GERA AS OPÇÕES AQUI
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

            # Salva no Banco (Reutiliza a mesma tabela!)
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
                           opcoes=session['opcoes_flash'], # Envia as 3 opções
                           feedback=feedback,
                           cor_feedback=cor_feedback,
                           acertou=acertou)

if __name__ == '__main__':
    app.run(debug=True)