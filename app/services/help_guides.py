"""
The user guides (Ajuda), PT-PT - one source for the Ajuda panel and for the AI assistant.

Two kinds:
- "module": how a whole circuit works, from start to end, each step with the screen it happens on (link -> "Ir");
- "page": one screen - what it is for, its steps, its frequent errors - opened by itself on that screen (path); it may
  point to its circuit (module).

A guide is shown only to who may open its screens, by the same rules as the menu: `perms` (any of them - a sector
without the screen has not got them, e.g. the Farmácia's), `requires` (all of them, e.g. Matéria-prima needs the
Produção sector's recipes:view too) and/or `roles`. An "Ir" towards a screen the user may not open is removed. Write the button names exactly as they
appear on the screen; a link is a route of frontend/src/App.jsx (checked by tests/test_help_guides.py).
"""
import re
import unicodedata

S = dict  # a step with its screen: S(text=..., link=...)

MODULES = [
    {
        "id": "compras", "title": "Compras e fornecedores",
        "perms": ["purchases:view", "suppliers:manage"],
        "intro": "O circuito de uma compra: o fornecedor, a sua fatura, a entrada da mercadoria em stock, o pagamento e o "
                 "IVA que a empresa pode deduzir.",
        "steps": [
            S(text="Registe o fornecedor: «Novo fornecedor», com o nome, o NIF e as condições de pagamento.", link="/fornecedores"),
            S(text="Registe a fatura recebida: «Nova fatura de compra» - tipo de documento, n.º do documento do fornecedor, "
                   "data e as linhas com o preço sem IVA e a taxa de IVA que o fornecedor cobrou.", link="/compras"),
            S(text="Para a mercadoria entrar em stock, marque «Dar entrada em stock dos produtos» e escolha o armazém: a "
                   "entrada é feita na mesma operação e atualiza o custo médio dos produtos.", link="/compras"),
            S(text="Para pagar, marque em Faturas de compra as faturas em dívida e clique em «Pagar», indicando de onde sai o "
                   "dinheiro.", link="/compras"),
            S(text="Os pagamentos ficam em Pagamentos a fornecedores. Um pagamento errado anula-se com o motivo: as faturas "
                   "voltam a estar em dívida.", link="/pagamentos-fornecedores"),
            S(text="O IVA dedutível das compras entra no Apuramento do IVA do mês.", link="/apuramento-iva"),
        ],
        "errors": [
            ("A fatura do fornecedor é recusada como repetida", "O mesmo documento do fornecedor só se regista uma vez (a "
             "não ser que o primeiro registo tenha sido anulado)."),
            ("A anulação de uma compra é recusada", "A compra deu entrada em stock e esse stock já saiu: a anulação "
             "retiraria do armazém o que já não existe."),
        ],
    },
    {
        "id": "caixa-tesouraria", "title": "Caixa e tesouraria",
        "perms": ["pos:view", "tesouraria:overview"],
        "intro": "O dinheiro do dia: cada caixa abre a sua sessão, vende, faz as suas entradas, saídas e transferências, e "
                 "fecha contando a gaveta. O gestor acompanha todas as caixas na Tesouraria.",
        "steps": [
            S(text="O gestor associa cada utilizador de caixa ao seu ponto de venda: separador Atividades, «Associar "
                   "utilizador».", link="/company-settings?tab=atividades"),
            S(text="O caixa abre a sessão com «Abrir caixa»: o fundo vem da sessão anterior.", link="/caixa"),
            S(text="Vende: Fatura/Recibo (paga no momento), Fatura (paga mais tarde, com recibo depois) ou Pro-forma."),
            S(text="Durante o dia, em Operações de Caixa (barra à esquerda): entradas e saídas externas com o seu motivo, e "
                   "transferências para outra caixa - a caixa de destino confirma a receção."),
            S(text="O recibo de uma Fatura paga mais tarde emite-se na caixa (Consultar documentos) ou em Faturas, «Emitir "
                   "Recibo».", link="/invoices"),
            S(text="No fim do dia, «Fechar caixa»: o valor contado na gaveta, e o motivo de uma diferença."),
            S(text="O gestor vê a Posição de cada caixa, os Movimentos e os Fechos em Finanças → Tesouraria.", link="/tesouraria"),
        ],
        "errors": [
            ("Uma transferência fica «Em trânsito»", "A caixa de destino ainda não confirmou a receção (Operações de Caixa). "
             "Enquanto houver transferências por receber, o período não fecha."),
        ],
    },
    {
        "id": "stock-circuito", "title": "Stock",
        "perms": ["warehouses:view", "stock:view"],
        "intro": "Por onde passa a mercadoria: entra no armazém principal, segue para o armazém de cada atividade e sai "
                 "pelas vendas, guias, consumos e perdas. Cada movimento fica registado.",
        "steps": [
            S(text="No produto, marque «Gerido por stocks» (e «Gerido por lotes» / «Gerido por validade» quando aplicável).", link="/products"),
            S(text="Entradas: uma fatura de compra com entrada em stock, ou «Registar Receção de Stock».", link="/compras"),
            S(text="Abasteça cada atividade com «Transferir stock» do armazém principal para o armazém da atividade.", link="/stock"),
            S(text="As vendas da caixa retiram o stock do armazém da atividade."),
            S(text="A mercadoria que viaja leva uma guia: Remessa (para um cliente), Transporte (entre armazéns) ou Devolução "
                   "(para um fornecedor).", link="/guias"),
            S(text="O que a empresa gasta ela própria (limpeza, amenities) regista-se em Consumo Interno, sem fatura.", link="/consumo-interno"),
            S(text="Corrija com «Ajustar stock» ou «Registar perda», e conte um armazém inteiro com «Inventário».", link="/stock"),
            S(text="Consulte o Resumo de Stock (valores, stock baixo, validades) e o Histórico de Movimentos.", link="/stock/dashboard"),
        ],
    },
    {
        "id": "fim-do-mes", "title": "Fim do mês",
        "perms": ["fiscal_periods:close", "vat:return", "saf_t:export"],
        "intro": "O que fazer no fim de cada mês para fechar as contas e cumprir as obrigações com a AGT.",
        "steps": [
            S(text="Feche todas as caixas e confirme as transferências pendentes.", link="/tesouraria"),
            S(text="Registe as faturas de compra do mês que faltam.", link="/compras"),
            S(text="«Fechar parcialmente» o período: as vendas param, os lançamentos internos atrasados ainda são aceites. "
                   "Abra o período seguinte para continuar a vender.", link="/fiscal-periods"),
            S(text="Confira o Apuramento do IVA do mês: «Ver documentos» mostra os documentos de cada linha.", link="/apuramento-iva"),
            S(text="Exporte o ficheiro SAF-T do mês e entregue-o à AGT.", link="/saf-t"),
            S(text="Quando tudo estiver certo, «Fechar definitivamente» o período: nunca mais reabre.", link="/fiscal-periods"),
        ],
        "tips": [
            "Nas Definições da Empresa pode exigir um inventário antes do fecho e congelar o stock de cada período fechado.",
        ],
    },
    {
        "id": "producao", "title": "Produção",
        "perms": ["recipes:view"],
        "intro": "Fabricar os próprios produtos (pão, bolos, pratos): as matérias-primas, a receita de cada produto e a "
                 "produção, que consome as matérias-primas e faz entrar o produto acabado.",
        "steps": [
            S(text="Registe as matérias-primas: «Nova matéria-prima» (não se vendem, não têm IVA).", link="/materia-prima"),
            S(text="Registe o produto acabado como qualquer produto.", link="/products"),
            S(text="Em Produtos configurados, «Configurar receita»: os ingredientes por lote e o rendimento do lote (quantas "
                   "unidades 1 lote produz). «Guardar receita».", link="/producao"),
            S(text="«Produzir»: a quantidade e o armazém - as matérias-primas saem do stock e o produto acabado entra.", link="/producao"),
            S(text="O Resumo de Produção mostra os lotes produzidos e as matérias-primas consumidas.", link="/producao/historico"),
        ],
        "errors": [
            ("«Excede a capacidade estimada com o stock atual de ingredientes»", "Faltam matérias-primas no armazém para "
             "essa quantidade: dê entrada delas primeiro."),
        ],
    },
    {
        "id": "restaurante", "title": "Restaurante e bar",
        "perms": ["open_accounts:view", "kitchen:view"],
        "intro": "O serviço à mesa: uma conta aberta por mesa, os pratos enviados para a cozinha, e a conta fechada na caixa "
                 "com um documento como qualquer venda.",
        "steps": [
            S(text="Crie as mesas como recursos da atividade (ex.: Mesa 4) - ou dê apenas um nome a cada conta.", link="/recursos"),
            S(text="«Abrir conta» numa mesa e junte os artigos à medida que são pedidos.", link="/contas-abertas"),
            S(text="Os artigos «Preparado na cozinha» seguem com «Enviar para cozinha».", link="/contas-abertas"),
            S(text="A cozinha vê os pedidos no seu ecrã (atualizado a cada 15 segundos) e marca cada prato «Pronto».", link="/cozinha"),
            S(text="Para separar clientes da mesma mesa, use «Dividir (nova conta)».", link="/contas-abertas"),
            S(text="«Fechar conta» na caixa: o documento é emitido e o stock sai, como numa venda normal. O atendente não "
                   "fecha contas.", link="/caixa"),
            S(text="O histórico da cozinha mostra quem fez cada prato e quanto tempo demorou.", link="/cozinha/historico"),
        ],
    },
    {
        "id": "reservas", "title": "Reservas e hotel",
        "perms": ["bookings:view", "resources:manage"],
        "intro": "Reservar quartos, praticantes ou mesas: a reserva, o check-in que abre a conta da estadia, os extras, e o "
                 "pagamento na caixa.",
        "steps": [
            S(text="Crie os recursos de cada atividade: «Novo recurso» (ex.: Quarto 101, Mesa 4).", link="/recursos"),
            S(text="Crie os serviços de tarifa (ex.: diária, 1 hora) - com duração, se for um serviço por tempo.", link="/services"),
            S(text="«Nova reserva»: o recurso, o cliente, as datas e o serviço. Duas reservas do mesmo recurso nunca se "
                   "sobrepõem.", link="/reservas"),
            S(text="«Check-in»: abre a conta do quarto, já com a tarifa calculada pela duração da estadia. Os extras (bar, "
                   "restaurante) juntam-se a essa conta.", link="/reservas"),
            S(text="A estadia paga-se na caixa (barra à esquerda: Reservas ou Contas abertas): fechar a conta conclui a "
                   "reserva. «Check-out» só termina uma estadia sem nada a pagar.", link="/caixa"),
            S(text="O histórico mostra cada utilização dos recursos, com o documento e a receita.", link="/recursos/historico"),
        ],
    },
    {
        "id": "farmacia", "title": "Farmácia",
        "perms": ["pharmacy:registers"],
        "intro": "Os medicamentos, as receitas, as seguradoras e os registos exigidos pela inspeção.",
        "steps": [
            S(text="No produto, marque «Medicamento»: substância ativa, forma farmacêutica, dosagem e o regime (livre, "
                   "receita ou receita especial). Um medicamento é sempre seguido por lote e validade.", link="/products"),
            S(text="Na venda, um medicamento de receita pede o n.º da receita - sempre, ou só quando o cliente a apresenta, "
                   "conforme as Definições da Empresa. A receita especial (psicotrópicos) pede-o sempre.",
              link="/company-settings?tab=dados"),
            S(text="Uma seguradora ou convénio é um cliente marcado «Entidade comparticipante», com a sua taxa.", link="/customers"),
            S(text="Na caixa, «Seguradora / convénio»: a entidade, o n.º do cartão do beneficiário e a taxa. Saem dois "
                   "documentos: o do utente (a sua parte) e a Fatura da seguradora (paga mais tarde com um Recibo).", link="/caixa"),
            S(text="As validades: Armazéns e Stock, separador Validades. Um lote expirado nunca é vendido.", link="/stock"),
            S(text="Os registos de receitas, de psicotrópicos e as comparticipações: Receitas e registos, para imprimir.", link="/receitas"),
        ],
    },
]

# The platform's own guides (SUPER_ADMIN): creating and following the client companies, the platform's settings.
PLATFORM_MODULES = [
    {
        "id": "novo-cliente", "title": "Novo cliente: da criação à primeira fatura", "roles": ["SUPER_ADMIN"],
        "intro": "Tudo o que a RM SOFT faz para pôr uma empresa cliente a trabalhar: a criação, os seus setores, o "
                 "endereço, a entrega ao gestor e o acompanhamento da sua configuração.",
        "steps": [
            S(text="Antes do primeiro cliente, confira os catálogos da plataforma: regimes fiscais, taxas legais de IVA, "
                   "tipos de documento e os Módulos (setores) com as funções que cada um dá.", link="/configuracoes"),
            S(text="Empresas → «Nova empresa». Separador Base (opcional): escolha a cópia exportada de uma empresa já "
                   "configurada (ex.: um «Comércio geral» preparado uma vez) e marque o que copiar - artigos e categorias, "
                   "serviços, fornecedores. A nova empresa fica com o regime fiscal dessa empresa. Nunca são copiados "
                   "clientes, stock, custos nem documentos.", link="/admin/companies"),
            S(text="Separador Conta do Gestor: o nome, o telefone e a palavra-passe da pessoa que vai gerir a empresa."),
            S(text="Separador Dados da Empresa: NIF, denominação fiscal, nome curto, o endereço (subdomínio, proposto a partir "
                   "do nome curto), contactos, regime fiscal, n.º de registo comercial (exigido no SAF-T) e o modo de emissão."),
            S(text="Separador Módulos: os setores contratados (Farmácia, Hotel, Restaurante…). Decidem os menus, os ecrãs e "
                   "os guias que a empresa vê. Coordenadas Bancárias é opcional."),
            S(text="«Criar empresa»: a empresa nasce com o seu armazém, as suas taxas de IVA e a conta do gestor."),
            S(text="Entregue ao gestor o endereço da empresa (ex.: farmacia-da-luz.rmsystem.co.ao), o telefone e a "
                   "palavra-passe. Ao entrar, ele vê a lista «Configuração inicial» no Painel."),
            S(text="Acompanhe-o: Empresas → lápis → separador «Configuração inicial» mostra o que falta, lido dos dados reais. "
                   "Os passos marcados «RM SOFT» (registo comercial, regime fiscal) são seus.", link="/admin/companies"),
            S(text="Se a empresa contratou o assistente, ative-o no separador Assistente IA (com o limite de mensagens).", link="/admin/companies"),
        ],
        "errors": [
            ("«Já existe uma empresa registada com…»", "NIF, nome, email e telefone da empresa são únicos na plataforma."),
            ("«O subdomínio … já é usado por outra empresa»", "Cada empresa tem o seu endereço: acrescente a cidade ou um "
             "número (ex.: farmacia-da-luz-viana)."),
        ],
    },
    {
        "id": "manter-clientes", "title": "Acompanhar as empresas clientes", "roles": ["SUPER_ADMIN"],
        "intro": "O dia a dia da plataforma depois da criação: ajudar um gestor, mudar um contrato, suspender uma empresa.",
        "steps": [
            S(text="Gestor sem acesso: Empresas → lápis → «Redefinir palavra-passe do Gestor». Os outros utilizadores são "
                   "geridos pelo próprio gestor (Administração → Utilizadores).", link="/admin/companies"),
            S(text="Novo setor contratado: separador Módulos da empresa. Antes de retirar um, veja em Visão global → Impacto "
                   "se a empresa já tem dados nessa função.", link="/visao-global"),
            S(text="Mudança de regime fiscal: separador Dados da Empresa. Vale a partir de hoje, fica no histórico de regimes e "
                   "atualiza as taxas de IVA da empresa; os documentos já emitidos não mudam."),
            S(text="Mudança de endereço: separador Dados da Empresa. O endereço antigo deixa de funcionar de imediato: avise o "
                   "gestor."),
            S(text="Suspender uma empresa (falta de pagamento, fim de contrato): desative-a na lista. No serviço hospedado "
                   "(SaaS), ninguém dessa empresa consegue entrar e as sessões abertas terminam em menos de 30 minutos. Os "
                   "dados ficam guardados.", link="/admin/companies"),
        ],
    },
]

PAGES = [
    {
        "id": "primeiros-passos", "path": "/dashboard", "title": "Primeiros passos", "perms": ["company:manage"],
        "intro": "Antes de faturar, a empresa precisa de alguns dados. A lista «Configuração inicial» (no Painel e no topo "
                 "da Ajuda) mostra o que falta e marca cada passo sozinho quando estiver feito.",
        "steps": [
            "Complete os dados da empresa: Administração → Empresa → Dados da Empresa (morada, cidade, contactos, logótipo).",
            "Verifique a atividade e os seus pontos de venda: separador Atividades. Cada atividade tem o seu armazém e a sua caixa.",
            "Confirme que o exercício e o período do mês estão abertos: Finanças → Períodos/Exercício.",
            "Registe o que vende: Catálogo → Produtos (e Serviços, se for o caso).",
            "Crie as contas da equipa (Administração → Utilizadores) e associe cada utilizador de caixa ao seu ponto de "
            "venda (Empresa → Atividades → Associar utilizador).",
            "Para enviar faturas por email, configure o separador Email da empresa.",
        ],
        "errors": [("O registo comercial ou o regime fiscal não estão marcados", "São definidos pela RM SOFT: contacte o suporte.")],
    },
    {
        "id": "caixa", "path": "/caixa", "title": "Caixa", "module": "caixa-tesouraria", "perms": ["pos:view"],
        "intro": "Vender ao balcão: abrir a sessão da caixa, registar as vendas e fechar a caixa no fim do dia, contando o numerário.",
        "steps": [
            "Confirme o ponto de venda no topo à direita. O gestor pode escolher entre vários; os outros utilizadores "
            "trabalham na caixa a que estão associados.",
            "Clique em «Abrir caixa». O fundo de abertura vem da sessão anterior.",
            "Pesquise o produto (nome ou código) ou leia o código de barras e prima Enter. O artigo vai para o Carrinho; "
            "ajuste a quantidade ou aplique um desconto na linha.",
            "Escolha o tipo de documento: Fatura/Recibo (paga no momento), Fatura (paga mais tarde) ou Pro-forma. Escolha o "
            "cliente quando o documento o exige (ou crie-o com «Novo cliente»).",
            "Indique as formas de pagamento e clique em «Confirmar venda» («Faturar» para uma Fatura, «Gerar pro-forma» para "
            "uma Pro-forma). O documento é emitido e pode ser impresso.",
            "No fim do dia, clique em «Fechar caixa», escreva o valor contado na gaveta e conclua. Uma diferença exige um motivo.",
        ],
        "tips": [
            "A barra à esquerda abre: Consultar documentos (reimprimir, emitir recibo, liquidar uma pro-forma), Consultar "
            "artigos, Moedeiro, Operações de Caixa (entradas, saídas e transferências entre caixas), Relatórios e Contas abertas.",
            "Passe o rato sobre «Numerário na gaveta» para ver tudo o que foi recebido na sessão, por forma de pagamento.",
        ],
        "errors": [
            ("«Nenhuma caixa associada»", "O gestor associa o utilizador a um ponto de venda em Administração → Empresa → "
             "Atividades → Associar utilizador."),
            ("A venda é recusada por causa do período", "O período do mês tem de estar aberto: Finanças → Períodos/Exercício."),
            ("Stock insuficiente", "Receba o stock no armazém da atividade (Stock → Armazéns e Stock) ou transfira-o do "
             "armazém principal."),
        ],
    },
    {
        "id": "faturas", "path": "/invoices", "title": "Faturas", "module": "caixa-tesouraria",
        "perms": ["invoices:view"], "roles": ["GESTOR"],
        "intro": "Todos os documentos de venda da empresa (Faturas, Faturas/Recibo, Pro-formas, Orçamentos, Notas de Crédito "
                 "e Débito): consultar, emitir fora da caixa, converter e corrigir.",
        "steps": [
            "Pesquise por série/número ou ATCUD. Abra o detalhe para ver as linhas, o IVA, o hash e o estado de envio à AGT.",
            "Para emitir sem passar pela caixa, clique em «Nova fatura», escolha o tipo, o cliente e os produtos, e clique "
            "em «Criar Fatura».",
            "Para receber o pagamento de uma Fatura, use «Emitir Recibo» nas ações da linha.",
            "Uma Pro-forma ou um Orçamento aceite converte-se em Fatura com «Converter».",
            "Um documento emitido nunca se apaga nem se altera: para o corrigir, emita uma «Nota de Crédito» (anula total ou "
            "parcialmente) ou uma «Nota de Débito» (acrescenta).",
        ],
        "errors": [
            ("Estado «Erro» no envio à AGT", "Use «Reenviar para a AGT» na linha. Os documentos ficam guardados mesmo sem "
             "internet e são enviados depois."),
            ("Não aparece «Emitir Nota de Crédito»", "O documento já foi retificado, ou o tipo não aceita nota de crédito "
             "(Pro-forma, Orçamento)."),
        ],
    },
    {
        "id": "clientes", "path": "/customers", "title": "Clientes", "perms": ["customers:manage"],
        "intro": "A ficha dos clientes da empresa: nome, NIF, contactos e condições. O cliente aparece nos documentos emitidos para ele.",
        "steps": [
            "Clique em «Novo cliente», preencha o nome e o NIF e clique em «Criar cliente».",
            "Pesquise por código, nome ou NIF. Abra a ficha para alterar os dados e ver as faturas do cliente.",
            "Uma venda sem cliente identificado vai para o «Consumidor Final».",
        ],
        "errors": [("«Já existe um cliente registado com este NIF»", "O NIF é único na empresa: use o cliente existente.")],
    },
    {
        "id": "produtos", "path": "/products", "title": "Produtos", "module": "stock-circuito", "perms": ["products:manage"],
        "intro": "A ficha dos produtos vendidos: código, preço, IVA, unidades e embalagens, e a forma como o stock é gerido.",
        "steps": [
            "Clique em «Novo produto». No separador Geral, indique o código, o nome, o preço e a taxa de IVA.",
            "Uma taxa de IVA de 0 % exige o motivo de isenção (obrigatório na AGT).",
            "No separador «Unidades e embalagens», defina as embalagens vendidas (ex.: caixa de 12) com o seu fator e preço.",
            "Marque «Gerido por stocks» para controlar as quantidades; «Gerido por lotes» e «Gerido por validade» para "
            "seguir lotes e datas de validade.",
            "Clique em «Criar produto». O separador «Histórico do custo» mostra a evolução do custo médio.",
        ],
        "tips": ["«Não disponível POS» esconde o produto da caixa (vende-se apenas por fatura)."],
        "errors": [("O produto não aparece na caixa", "Verifique o estado (Ativo), a opção «Não disponível POS» e o stock no "
                    "armazém da atividade.")],
    },
    {
        "id": "servicos", "path": "/services", "title": "Serviços", "perms": ["services:manage"],
        "intro": "A ficha dos serviços vendidos (sem stock): mão de obra, lavandaria, tarifas de quarto, marcações.",
        "steps": [
            "Clique em «Novo serviço»: código, nome, preço e taxa de IVA (0 % exige o motivo de isenção).",
            "Para as reservas, um serviço pode ter uma duração (ex.: massagem de 60 min) e um tipo de recurso (ex.: só para "
            "quartos).",
            "«Não disponível POS» esconde o serviço da caixa.",
        ],
    },
    {
        "id": "materia-prima", "path": "/materia-prima", "title": "Matéria-prima", "module": "producao",
        "perms": ["products:manage"], "requires": ["recipes:view"],
        "intro": "Os ingredientes e materiais usados na produção: seguidos em stock, nunca vendidos (sem preço nem IVA).",
        "steps": [
            "Clique em «Nova matéria-prima»: código, nome, unidade base e limite mínimo de stock.",
            "Marque «Gerido por lotes» / «Gerido por validade» para seguir lotes e datas.",
            "As matérias-primas entram em stock pelas faturas de compra e saem pela produção.",
        ],
    },
    {
        "id": "producao-receitas", "path": "/producao", "title": "Produtos configurados", "module": "producao",
        "perms": ["recipes:view"],
        "intro": "A receita de cada produto fabricado e a produção.",
        "steps": [
            "«Configurar receita»: o produto, os ingredientes por lote (quantidade e unidade) e o rendimento do lote. "
            "«Guardar receita».",
            "«Produzir»: a quantidade a produzir e o armazém. As matérias-primas saem e o produto acabado entra no stock.",
        ],
        "errors": [("«Excede a capacidade estimada com o stock atual de ingredientes»", "Faltam matérias-primas no armazém "
                    "para essa quantidade.")],
    },
    {
        "id": "producao-historico", "path": "/producao/historico", "title": "Resumo de Produção", "module": "producao",
        "perms": ["recipes:view"],
        "intro": "O histórico dos lotes produzidos e das matérias-primas consumidas em cada um.",
        "steps": ["Escolha o período e abra um lote para ver o que consumiu."],
    },
    {
        "id": "stock", "path": "/stock", "title": "Armazéns e Stock", "module": "stock-circuito", "perms": ["warehouses:view"],
        "intro": "As quantidades de cada produto em cada armazém: receber stock, transferir entre armazéns, ajustar e inventariar.",
        "steps": [
            "Escolha o armazém. O armazém principal recebe as compras; cada atividade vende a partir do seu próprio armazém.",
            "Para dar entrada de mercadoria, use «Registar Receção de Stock».",
            "Para abastecer uma atividade, use «Transferir stock» do armazém principal para o armazém da atividade.",
            "Para corrigir uma quantidade, use «Ajustar stock» com o motivo; para uma quebra, «Registar perda».",
            "Para contar todo um armazém, use «Inventário».",
            "O separador «Validades» mostra os lotes expirados ou a expirar.",
        ],
        "errors": [
            ("A saída é recusada por falta de stock", "O armazém não permite quantidades negativas: dê entrada ou transfira o "
             "stock primeiro."),
            ("«Entradas bloqueadas» ou «Saídas bloqueadas»", "O armazém foi bloqueado na sua ficha: abra-a com o lápis e "
             "desmarque a opção."),
        ],
    },
    {
        "id": "stock-resumo", "path": "/stock/dashboard", "title": "Resumo de Stock", "module": "stock-circuito",
        "perms": ["stock:view"],
        "intro": "A visão de todo o stock: quantidades, valor ao custo médio e à venda, margem, stock baixo ou a zero, lotes a "
                 "expirar.",
        "steps": [
            "Sem período, mostra o stock de hoje; com um período fiscal, o stock no fim desse período, com o inicial, as "
            "entradas, as saídas e o final.",
            "Pesquise um produto para ver o seu stock em cada armazém.",
        ],
    },
    {
        "id": "movimentos", "path": "/stock-movements", "title": "Histórico de Movimentos", "module": "stock-circuito",
        "perms": ["stock:view"],
        "intro": "Cada entrada e saída de stock, com a data, o armazém, o lote e o motivo ou documento de origem.",
        "steps": [
            "Pesquise por produto, referência ou motivo.",
            "Uma transferência aparece numa só linha, «origem → destino».",
        ],
    },
    {
        "id": "consumo", "path": "/consumo-interno", "title": "Consumo Interno", "module": "stock-circuito",
        "perms": ["internal_consumption:view"],
        "intro": "O que a empresa usa ela própria (limpeza, amenities…): retira do stock sem emitir fatura.",
        "steps": [
            "Clique em «Registar consumo»: o produto, a quantidade, o motivo e, se quiser, o recurso (ex.: o quarto) e notas.",
            "Os motivos de consumo geram-se em Administração → Catálogos.",
        ],
    },
    {
        "id": "fornecedores", "path": "/fornecedores", "title": "Fornecedores", "module": "compras", "perms": ["suppliers:manage"],
        "intro": "As entidades a quem a empresa compra, com o saldo em dívida de cada uma.",
        "steps": [
            "Clique em «Novo fornecedor»: nome, NIF, país e, se quiser, contactos e condições de pagamento. «Criar fornecedor».",
            "A coluna «Saldo em dívida» mostra o que falta pagar a cada fornecedor.",
        ],
    },
    {
        "id": "compras-faturas", "path": "/compras", "title": "Faturas de compra", "module": "compras",
        "perms": ["purchases:view"],
        "intro": "As faturas recebidas dos fornecedores: o registo, a entrada em stock, o pagamento e a anulação.",
        "steps": [
            "«Nova fatura de compra»: fornecedor, tipo de documento, n.º do documento do fornecedor, data do documento e "
            "vencimento.",
            "As linhas: artigo ou descrição, quantidade, preço sem IVA e a taxa de IVA do fornecedor.",
            "Marque «Dar entrada em stock dos produtos» e escolha o armazém para a mercadoria entrar já.",
            "«Registar fatura de compra». Para pagar, marque as faturas em dívida e clique em «Pagar».",
            "Um registo errado não se apaga: «Anular» com o motivo.",
        ],
        "tips": ["Uma nota de crédito do fornecedor indica a fatura corrigida e reduz o IVA dedutível; não mexe no stock."],
    },
    {
        "id": "pagamentos", "path": "/pagamentos-fornecedores", "title": "Pagamentos a fornecedores", "module": "compras",
        "perms": ["purchases:view"],
        "intro": "Os pagamentos feitos aos fornecedores, cada um com as faturas que liquidou e de onde saiu o dinheiro.",
        "steps": [
            "Os pagamentos registam-se em Faturas de compra (marcar as faturas e «Pagar»); aqui consultam-se.",
            "Um pagamento errado anula-se com o motivo: as faturas voltam a estar em dívida e o dinheiro volta à sua caixa.",
        ],
    },
    {
        "id": "guias", "path": "/guias", "title": "Guias", "module": "stock-circuito", "perms": ["guias:view"],
        "intro": "Os documentos que acompanham a mercadoria: Guia de Remessa (para um cliente), de Transporte (entre dois "
                 "armazéns da empresa) e de Devolução (para um fornecedor). Movimentam o stock.",
        "steps": [
            "«Nova guia»: escolha o tipo, os locais de carga e descarga, o destinatário, a viatura e o início do transporte.",
            "Junte os artigos e emita a guia: tem série, hash e ATCUD, como uma fatura.",
            "As guias de remessa de um cliente faturam-se juntas com «Faturar guias de remessa»: uma só Fatura, sem tirar "
            "outra vez a mercadoria do stock.",
            "Uma guia errada anula-se com o motivo e a mercadoria volta. Uma guia já faturada não se anula.",
        ],
    },
    {
        "id": "tesouraria", "path": "/tesouraria", "title": "Tesouraria", "module": "caixa-tesouraria",
        "perms": ["tesouraria:overview"],
        "intro": "A vista do gestor sobre o dinheiro de todas as caixas. Só consulta: as operações fazem-se na Caixa.",
        "steps": [
            "Posição: cada caixa agora (aberta ou fechada, quem a abriu, o numerário).",
            "Movimentos: transferências, entradas e saídas externas de um período, com o estado («Em trânsito» ou «Recebido»).",
            "Fechos: cada fecho com o esperado, o contado e a diferença; o relatório de fecho imprime-se.",
        ],
    },
    {
        "id": "periodos", "path": "/fiscal-periods", "title": "Períodos e exercício", "module": "fim-do-mes",
        "perms": ["fiscal_periods:view"],
        "intro": "O ano fiscal e os seus meses. Só se vende e se fatura num período aberto: um período fechado recusa qualquer "
                 "operação, com uma mensagem clara.",
        "steps": [
            "No início de cada ano, clique em «Abrir ano fiscal»; no início de cada mês, em «Abrir período».",
            "No fim do mês, «Fechar parcialmente» o período: deixa de aceitar vendas, mas ainda aceita os lançamentos "
            "internos atrasados (compras, stock).",
            "Quando tudo estiver lançado, «Fechar definitivamente». Um período fechado definitivamente nunca reabre.",
            "O ano fecha-se do mesmo modo, depois de Dezembro.",
        ],
        "errors": [
            ("Não consigo abrir o próximo ano", "Feche primeiro o ano atual (parcial ou definitivamente)."),
            ("Não consigo fechar o período", "Feche todas as sessões de caixa e confirme a receção das transferências de "
             "caixa pendentes."),
        ],
    },
    {
        "id": "apuramento-iva", "path": "/apuramento-iva", "title": "Apuramento do IVA", "module": "fim-do-mes",
        "perms": ["vat:return"],
        "intro": "O IVA de um mês, para todas as atividades: o liquidado nas vendas (as notas de crédito em menos), o "
                 "dedutível nas compras, e o resultado.",
        "steps": [
            "Escolha o período.",
            "Cada linha (por taxa) abre os documentos que a compõem com «Ver documentos»; cada documento abre-se (PDF ou "
            "fatura de compra).",
            "É só consulta: para corrigir, corrija o documento de origem (nota de crédito, anulação da compra).",
        ],
    },
    {
        "id": "saf-t", "path": "/saf-t", "title": "SAF-T", "module": "fim-do-mes", "perms": ["saf_t:export"],
        "intro": "O ficheiro SAF-T (AO) com os documentos do mês, a entregar à AGT.",
        "steps": [
            "Escolha o ano fiscal e o mês.",
            "Clique em «Exportar ficheiro SAF-T» e guarde o ficheiro XML.",
        ],
        "errors": [("Falta o n.º de registo comercial", "É exigido no ficheiro: definido pela RM SOFT, contacte o suporte.")],
    },
    {
        "id": "recursos", "path": "/recursos", "title": "Recursos", "module": "reservas", "perms": ["resources:manage"],
        "intro": "O que se reserva ou se ocupa: quartos, mesas, praticantes (cabeleireiro, massagista).",
        "steps": [
            "Clique em «Novo recurso»: a atividade, o nome (ex.: Quarto 101, Mesa 4), o tipo de recurso e, se quiser, a capacidade.",
            "Os tipos de recurso geram-se em Administração → Catálogos.",
        ],
    },
    {
        "id": "reservas-pagina", "path": "/reservas", "title": "Reservas", "module": "reservas", "perms": ["bookings:view"],
        "intro": "As reservas de quartos, praticantes, mesas ou qualquer recurso - a mesma lista que a receção vê na caixa.",
        "steps": [
            "«Nova reserva»: o recurso, o cliente (ou «Novo cliente»), as datas e o serviço.",
            "«Check-in» no dia da chegada: abre a conta da estadia com a tarifa.",
            "Para prolongar ou encurtar, indique a nova data de saída: a tarifa é recalculada.",
            "A conta paga-se na caixa; «Check-out» termina uma estadia sem nada a pagar.",
        ],
        "errors": [("A reserva é recusada", "O recurso já está reservado nessas datas: duas reservas nunca se sobrepõem.")],
    },
    {
        "id": "recursos-historico", "path": "/recursos/historico", "title": "Histórico dos recursos", "module": "reservas",
        "perms": ["resources:history"],
        "intro": "Cada utilização dos quartos, mesas e praticantes, com o documento e a receita (documentos menos notas de crédito).",
        "steps": [
            "Escolha a atividade e o período; filtre por recurso.",
            "As canceladas e as faltas («Não compareceu») aparecem à parte.",
        ],
    },
    {
        "id": "contas-abertas", "path": "/contas-abertas", "title": "Contas abertas", "module": "restaurante",
        "perms": ["open_accounts:view"],
        "intro": "As contas de mesa (ou de quarto) que acumulam artigos até serem fechadas na caixa.",
        "steps": [
            "«Abrir conta» numa mesa, ou «Nova conta nesta mesa» para outro grupo.",
            "Junte os artigos; os pratos «Preparado na cozinha» seguem com «Enviar para cozinha».",
            "«Dividir (nova conta)» separa artigos para outra conta.",
            "«Fechar conta» emite o documento - feito por quem tem acesso à caixa.",
        ],
        "errors": [("Uma conta sem artigos ficou aberta", "Anule-a com «Anular conta vazia».")],
    },
    {
        "id": "cozinha", "path": "/cozinha", "title": "Cozinha", "module": "restaurante", "perms": ["kitchen:view"],
        "intro": "Os pedidos enviados pela sala, um cartão por pedido, atualizados a cada 15 segundos (com um aviso sonoro).",
        "steps": [
            "Cada cartão mostra a mesa, quem o enviou e há quanto tempo.",
            "Avance prato a prato ou o cartão inteiro até «Pronto».",
            "«Prontos recentes» mostra o que acabou de sair.",
        ],
    },
    {
        "id": "cozinha-historico", "path": "/cozinha/historico", "title": "Histórico da cozinha", "module": "restaurante",
        "perms": ["kitchen:history"],
        "intro": "Os pedidos de um período e, em cada prato, quem o começou, quem o deu como pronto, quem o anulou e quanto "
                 "tempo demorou.",
        "steps": ["Escolha o período (hoje, ontem, semana…)."],
    },
    {
        "id": "receitas", "path": "/receitas", "title": "Receitas e registos", "module": "farmacia",
        "perms": ["pharmacy:registers"],
        "intro": "Os registos da farmácia, construídos a partir das vendas e do stock - nada a introduzir à mão.",
        "steps": [
            "Registo de receitas: cada venda com receita, os medicamentos e os lotes.",
            "Psicotrópicos e estupefacientes: por medicamento de receita especial, o stock inicial, cada entrada e saída "
            "(com a receita e o utente) e o stock final.",
            "Comparticipações: as vendas partilhadas com cada seguradora, a parte do utente e o que falta receber.",
            "Escolha o período e clique em «Imprimir» para a inspeção.",
        ],
    },
    {
        "id": "utilizadores", "path": "/users", "title": "Utilizadores", "roles": ["GESTOR"],
        "intro": "As contas de quem trabalha na empresa. Cada pessoa entra com o seu número de telefone e a sua palavra-passe.",
        "steps": [
            "Clique em «Novo utilizador», indique o nome completo, o número de telefone, a palavra-passe (mínimo 8 "
            "caracteres) e a função.",
            "Funções: Caixa (vende na caixa), Atendente (contas abertas), Cozinha (pedidos), Armazenista (stock), "
            "Contabilista (consulta e fiscal).",
            "Associe cada utilizador de caixa ao seu ponto de venda: Administração → Empresa → Atividades → Associar utilizador.",
            "O que cada função pode fazer ajusta-se em Administração → Permissões.",
            "Para um esquecimento, use «Redefinir palavra-passe». Uma conta desativada já não entra.",
        ],
        "errors": [("O número de telefone já existe", "O número é único na empresa: cada pessoa tem a sua conta.")],
    },
    {
        "id": "permissoes", "path": "/permissoes", "title": "Permissões", "roles": ["GESTOR"],
        "intro": "O que cada função (Caixa, Atendente, Cozinha, Armazenista, Contabilista) pode ver e fazer. O gestor pode tudo.",
        "steps": [
            "Marque ou desmarque cada permissão por função; a alteração vale para todos os utilizadores dessa função.",
            "Os menus e os botões acompanham: o que uma função não pode fazer deixa de aparecer.",
        ],
    },
    {
        "id": "catalogos", "path": "/categorias", "title": "Catálogos",
        "perms": ["product_categories:manage", "service_types:manage", "tesouraria:reasons_manage", "resource_types:manage",
                  "consumption_reasons:manage", "tesouraria:payment_prefs_manage", "pharmaceutical_forms:manage"],
        "intro": "As listas próprias da empresa usadas nos outros ecrãs: categorias de produtos, tipos de serviço, motivos de "
                 "caixa e de consumo, tipos de recurso, métodos de pagamento e condições de pagamento.",
        "steps": [
            "Abra o cartão da lista e clique em «Novo»; cada item pode ser editado ou desativado.",
            "Métodos de Pagamento: escolha os que aparecem na caixa, nas vendas e nas compras.",
        ],
    },
    {
        "id": "empresa", "path": "/company-settings", "title": "Definições da empresa", "perms": ["company:view"],
        "intro": "Os dados que aparecem nos documentos e a organização da empresa em atividades, pontos de venda e séries.",
        "steps": [
            "Dados da Empresa: morada, cidade, contactos, moedas, logótipo e as opções de faturação. Clique em «Guardar alterações».",
            "Atividades: cada atividade (loja, bar, hotel…) tem o seu armazém e os seus pontos de venda; associe aqui os "
            "utilizadores às caixas.",
            "Estabelecimentos: obrigatórios na faturação eletrónica (ex.: SEDE).",
            "Coordenadas Bancárias: o IBAN impresso nas faturas.",
            "Séries de Facturação: a numeração dos documentos por ano. No modo manual com série automática, são criadas na "
            "primeira emissão.",
            "Email: o servidor de envio (SMTP) da empresa, para enviar as faturas aos clientes.",
            "Cópias de segurança: escolha «Automática» (1 a 3 horas por dia) ou «Só manual», e «Fazer cópia agora» a "
            "qualquer momento. Cada cópia guarda todos os dados da empresa e pode ser descarregada; guardam-se as dos "
            "últimos 7 dias e uma por semana durante 4 semanas. A reposição de uma cópia é feita pela RM SOFT.",
        ],
        "errors": [("O NIF ou o nome não se alteram", "A identidade fiscal é definida pela RM SOFT: contacte o suporte.")],
    },
]


PLATFORM_PAGES = [
    {
        "id": "empresas", "path": "/admin/companies", "title": "Empresas", "module": "novo-cliente", "roles": ["SUPER_ADMIN"],
        "intro": "As empresas clientes da plataforma: criar, editar, acompanhar e suspender.",
        "steps": [
            "«Nova empresa» abre a criação, separador a separador: Base (o catálogo de uma cópia exportada), Conta do "
            "Gestor, Dados da Empresa, Coordenadas Bancárias, Módulos.",
            "O lápis abre uma empresa: os mesmos separadores, mais Taxas de IVA, Assistente IA e Configuração inicial. "
            "«Guardar alterações» grava tudo.",
            "Por baixo do nome de cada empresa aparece o seu endereço (subdomínio).",
            "«Redefinir palavra-passe do Gestor» dá uma nova palavra-passe ao gestor da empresa.",
            "O estado ativa / inativa suspende ou reativa a empresa inteira.",
            "O botão de descarga (seta para baixo) exporta uma cópia de segurança da empresa: um ficheiro .zip com todos os "
            "seus dados - documentos, clientes, artigos, stock, utilizadores e imagens. Guarde-o fora do servidor.",
            "«Cópias de segurança» mostra o estado das cópias de todas as empresas: modo, última cópia feita, erros e "
            "espaço ocupado - em vermelho, uma empresa ativa sem cópia há mais de um dia. As cópias de uma empresa: lápis → "
            "separador Cópias de segurança (descarregar, fazer uma agora).",
            "«Restaurar empresa» repõe uma empresa a partir dessa cópia, tal como estava no momento da cópia (mesmos "
            "documentos, numeração e palavras-passe) - depois de uma avaria, ou para a passar para outra instalação da "
            "mesma versão. Mostra primeiro o que o ficheiro contém; recusa se a empresa já existe aqui (nunca a substitui).",
        ],
    },
    {
        "id": "configuracoes", "path": "/configuracoes", "title": "Configurações da plataforma", "roles": ["SUPER_ADMIN"],
        "intro": "O que vale para todas as empresas: a identificação do software na AGT, o assistente IA, os canais e os "
                 "catálogos comuns.",
        "steps": [
            "Identificação do software (SAF-T): n.º de validação AGT, NIF do fornecedor, ProductID e versão - vão em cada "
            "ficheiro SAF-T de todas as empresas.",
            "Assistente IA: o fornecedor, o modelo, a chave (nunca mostrada de volta) e as mensagens por mês por empresa. "
            "Cada empresa é ativada em Empresas → Assistente IA.",
            "Bot do Telegram e WhatsApp RM SOFT: o token do @BotFather, e os valores da Meta para o WhatsApp.",
            "Catálogos: países, províncias, moedas, bancos, métodos e condições de pagamento, códigos e taxas legais de IVA, "
            "regimes fiscais, retenções, tipos de documento (com as suas regras), unidades, tipos de movimento e Módulos "
            "(os setores).",
        ],
        "errors": [
            ("Uma regra de tipo de documento não se altera", "As regras fiscais fixadas pela AGT estão bloqueadas."),
        ],
    },
    {
        "id": "visao-global", "path": "/visao-global", "title": "Visão global", "module": "manter-clientes",
        "roles": ["SUPER_ADMIN"],
        "intro": "Os setores, as funções e as empresas da plataforma, de um só olhar.",
        "steps": [
            "Setores: cada setor (Farmácia, Hotel…) e as funções que dá.",
            "Empresas: cada empresa com os seus setores e atividades.",
            "Funções: cada bloco de funcionalidades (stock, reservas, cozinha…), de que depende e os ecrãs que abre.",
            "Impacto: as empresas que já têm dados numa função que os seus setores não incluem - a verificar antes de "
            "retirar um setor.",
        ],
    },
]


def _normalized(guide: dict, kind: str) -> dict:
    steps = [s if isinstance(s, dict) else {"text": s} for s in guide["steps"]]
    return {"id": guide["id"], "kind": kind, "title": guide["title"], "path": guide.get("path"),
            "module": guide.get("module"), "intro": guide["intro"],
            "steps": [{"text": s["text"], "link": s.get("link")} for s in steps],
            "tips": list(guide.get("tips", [])), "errors": [list(e) for e in guide.get("errors", [])]}


def _allowed(guide: dict, permissions: set[str], role: str | None) -> bool:
    if guide.get("roles") and role not in guide["roles"]:
        return False
    if not set(guide.get("requires", [])) <= permissions:
        return False
    return not guide.get("perms") or any(p in permissions for p in guide["perms"])


def visible_guides(permissions: set[str], role: str | None) -> list[dict]:
    """The guides this user may read: the circuits first, then the pages. A page's link to its circuit is kept only
    when that circuit is visible too."""
    all_modules, all_pages = MODULES + PLATFORM_MODULES, PAGES + PLATFORM_PAGES
    modules = [_normalized(g, "module") for g in all_modules if _allowed(g, permissions, role)]
    module_ids = {m["id"] for m in modules}
    pages = [_normalized(g, "page") for g in all_pages if _allowed(g, permissions, role)]
    for page in pages:
        if page["module"] not in module_ids:
            page["module"] = None
    # an "Ir" only towards a screen the user may open (each screen's rule is its page guide's)
    closed = {g["path"] for g in all_pages} - {p["path"] for p in pages}
    for guide in modules + pages:
        for step in guide["steps"]:
            if step["link"] and step["link"].split("?")[0] in closed:
                step["link"] = None
    return modules + pages


def _fold(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


def _text(guide: dict) -> str:
    return " ".join([guide["title"], guide["intro"], *(s["text"] for s in guide["steps"]), *guide["tips"],
                     *(" ".join(e) for e in guide["errors"])])


# words of the question that say nothing of its subject (PT, and the FR / EN a user may write)
_STOPWORDS = {"como", "faco", "fazer", "faz", "para", "que", "onde", "qual", "quais", "serve", "posso", "pode", "uma",
              "uns", "umas", "com", "sem", "por", "dos", "das", "nos", "nas", "aos", "meu", "minha", "esta", "este",
              "comment", "pour", "est", "les", "des", "une", "faire", "how", "the", "what", "where"}


def search_guides(guides: list[dict], query: str, limit: int = 3) -> list[dict]:
    """The guides that best match a question (accents ignored): a word in the title counts 3, in the text 1."""
    words = [w for w in re.findall(r"[a-z0-9]+", _fold(query)) if len(w) > 2 and w not in _STOPWORDS]
    scored = []
    for guide in guides:
        body, title = _fold(_text(guide)), _fold(guide["title"])
        score = sum(3 if w in title else 1 if w in body else 0 for w in words)
        if score:
            scored.append((score, guide["kind"] == "module", guide))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [g for _, _, g in scored[:limit]]


def guide_as_text(guide: dict) -> str:
    """A guide written out for the AI: what it is, its numbered steps (with the screen), tips and frequent errors."""
    lines = [f"{'Como funciona' if guide['kind'] == 'module' else 'Ecrã'}: {guide['title']}", guide["intro"]]
    for i, step in enumerate(guide["steps"], 1):
        lines.append(f"{i}. {step['text']}")
    lines += [f"Dica: {t}" for t in guide["tips"]]
    lines += [f"Erro frequente: {p} -> {s}" for p, s in guide["errors"]]
    return "\n".join(lines)
