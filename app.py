from flask import Flask, render_template, request, session, redirect, url_for
import random
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    return render_template('menu.html')

@app.route('/iniciar/<modo>')
def iniciar(modo):
    session['modo'] = modo
    session['score'] = 0
    # Força gerar primeira pergunta
    return redirect(url_for('nova_pergunta'))

@app.route('/nova_pergunta')
def nova_pergunta():
    # Gera números e salva na sessão
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
    session['operador_visual'] = '÷' if op == '/' else ('x' if op == '*' else op)
    session['resposta_correta'] = resp
    
    # Limpa estados anteriores
    session.pop('feedback', None)
    session.pop('acertou', None)
    
    return redirect(url_for('jogo'))

@app.route('/jogo', methods=['GET', 'POST'])
def jogo():
    # Se não tiver pergunta na sessão (ex: reiniciou servidor), gera uma
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
                
                if resp_user == resp_real:
                    session['score'] += 1
                    feedback = "MUITO BEM! 🎉"
                    cor_feedback = "green"
                    acertou = True
                else:
                    feedback = "Ops! Tente de novo. 👇"
                    cor_feedback = "#D32F2F" # Vermelho
                    acertou = False
                    mostrar_ajuda = True # Mostra ajuda se errar
        except:
            pass

    # Gera o texto de ajuda baseado na operação atual
    dica = gerar_texto_ajuda(session['num1'], session['num2'], session['operador_real'])

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

def gerar_texto_ajuda(n1, n2, op):
    if op == '+': return f"Guarde o número {n1} na cabeça e conte mais {n2} dedos!"
    if op == '-': return f"Coloque {n1} dedos e abaixe {n2}. Quantos sobraram?"
    if op == '*': return f"Isso é o mesmo que somar o número {n1}, {n2} vezes."
    if op == '/': return f"Imagine dividir {n1} balas para {n2} amigos."
    return "Tente contar devagar!"

if __name__ == '__main__':
    app.run(debug=True)
