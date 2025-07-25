import discord
from discord import app_commands
from discord.ext import tasks
import json
import os
import sys
import difflib
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from json_manager import (
    ler_contas, salvar_contas, inicializar_json, 
    ler_tarefas, salvar_tarefas, adicionar_tarefa,
    ler_contas_mistas, salvar_contas_mistas,
    ler_contas_rebirth, salvar_contas_rebirth
)
import emoji
import re
import time
import base64
import requests
import cloudscraper


# --- Constantes de Arquivos ---
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # Diretório raiz do projeto
CONFIG_FILE = os.path.join(BASE_DIR, "config", "config.json")
BRAINROTS_CONFIG_FILE = os.path.join(BASE_DIR, "config", "brainrots_config.json")
LUCKY_BLOCKS_CONFIG_FILE = os.path.join(BASE_DIR, "config", "lucky_blocks_config.json")
CORES_CONFIG_FILE = os.path.join(BASE_DIR, "config", "cores_config.json")
MUTATIONS_CONFIG_FILE = os.path.join(BASE_DIR, "config", "mutations_config.json")
RENDA_TIERS_CONFIG_FILE = os.path.join(BASE_DIR, "config", "renda_tiers_config.json")
EMBED_COLOR = discord.Color(0xFE7130)

# --- Dicionários para Cache de Configuração ---
# Guardam os dados dos JSONs para evitar leituras repetidas do disco.
CONFIG_DATA = {}
BRAINROTS_DATA = []
LUCKY_BLOCKS_DATA = []
CORES_DATA = []
MUTATIONS_DATA = []
RENDA_TIERS_DATA = []

# --- Variáveis para Sistema de Vendas GGMAX ---
GGMAX_TOKEN = None
GGMAX_TOKEN_EXP = 0

CANAL_VENDAS_ID = None  # Será definido pelo config.json

# --- Funções de Carregamento e Cache ---

def carregar_configs_globais():
    """Carrega todos os arquivos de configuração para a memória."""
    global CONFIG_DATA, BRAINROTS_DATA, LUCKY_BLOCKS_DATA, CORES_DATA, MUTATIONS_DATA, RENDA_TIERS_DATA, CANAL_VENDAS_ID
    
    # Carrega config.json
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                CONFIG_DATA = json.load(f)
                # Carrega o ID do canal de vendas
                CANAL_VENDAS_ID = CONFIG_DATA.get("CANAL_DESTINO_ID")
                if CANAL_VENDAS_ID:
                    CANAL_VENDAS_ID = int(CANAL_VENDAS_ID)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[ERRO] Falha ao carregar {CONFIG_FILE}: {e}")
            CONFIG_DATA = {}

    # Carrega brainrots_config.json
    if os.path.exists(BRAINROTS_CONFIG_FILE):
        try:
            with open(BRAINROTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                BRAINROTS_DATA = json.load(f).get("brainrots", [])
        except (json.JSONDecodeError, IOError):
            BRAINROTS_DATA = []

    # Carrega lucky_blocks_config.json
    if os.path.exists(LUCKY_BLOCKS_CONFIG_FILE):
        try:
            with open(LUCKY_BLOCKS_CONFIG_FILE, "r", encoding="utf-8") as f:
                LUCKY_BLOCKS_DATA = json.load(f).get("lucky_blocks", [])
        except (json.JSONDecodeError, IOError):
            LUCKY_BLOCKS_DATA = []

    # Carrega cores_config.json
    if os.path.exists(CORES_CONFIG_FILE):
        try:
            with open(CORES_CONFIG_FILE, "r", encoding="utf-8") as f:
                CORES_DATA = json.load(f).get("cores", [])
        except (json.JSONDecodeError, IOError):
            CORES_DATA = []

    # Carrega mutations_config.json
    if os.path.exists(MUTATIONS_CONFIG_FILE):
        try:
            with open(MUTATIONS_CONFIG_FILE, "r", encoding="utf-8") as f:
                MUTATIONS_DATA = json.load(f).get("mutacoes", [])
        except (json.JSONDecodeError, IOError):
            MUTATIONS_DATA = []
            
    # Carrega renda_tiers_config.json
    if os.path.exists(RENDA_TIERS_CONFIG_FILE):
        try:
            with open(RENDA_TIERS_CONFIG_FILE, "r", encoding="utf-8") as f:
                RENDA_TIERS_DATA = json.load(f).get("tiers", [])
        except (json.JSONDecodeError, IOError):
            RENDA_TIERS_DATA = []

    print("[CONFIG] Configurações globais carregadas.")

# --- Funções de Autocomplete ---

async def nick_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    # Coleta nicks de contas normais
    data = ler_contas()
    nicks = [conta["nick"] for conta in data.get("contas", [])]
    
    # Adiciona nicks de contas rebirth
    data_rebirth = ler_contas_rebirth()
    nicks_rebirth = [conta["nick"] for conta in data_rebirth.get("contas_rebirth", [])]
    
    # Combina todas as listas de nicks
    todos_nicks = nicks + nicks_rebirth
    
    return [
        app_commands.Choice(name=nick, value=nick)
        for nick in todos_nicks if current.lower() in nick.lower()
    ][:25]

async def brainrot_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    for b in BRAINROTS_DATA:
        if isinstance(b, dict) and isinstance(b.get('nome'), str):
            if current.lower() in b['nome'].lower():
                choices.append(app_commands.Choice(name=b['nome'], value=b['nome']))
    return choices[:25]

async def cor_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    for c in CORES_DATA:
        if isinstance(c, dict) and isinstance(c.get('nome'), str):
            if current.lower() in c['nome'].lower():
                choices.append(app_commands.Choice(name=c['nome'], value=c['nome']))
    return choices[:25]

async def mutacao_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    for m in MUTATIONS_DATA:
        if isinstance(m, dict) and isinstance(m.get('nome'), str):
            if current.lower() in m['nome'].lower():
                choices.append(app_commands.Choice(name=m['nome'], value=m['nome']))
    return choices[:25]

async def faixa_renda_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete para as faixas de renda de contas mistas."""
    faixas = [tier['nome_faixa'] for tier in RENDA_TIERS_DATA if 'tipo' in tier and tier['tipo'] == 'misto']
    
    # Filtra as faixas baseadas no que o usuário digitou
    return [
        app_commands.Choice(name=faixa, value=faixa)
        for faixa in faixas if current.lower() in faixa.lower()
    ][:25]

async def nick_mista_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete para nicks de contas mistas."""
    data = ler_contas_mistas()
    contas = data.get("contas_mistas", [])
    nicks = [conta["nick"] for conta in contas]
    
    return [
        app_commands.Choice(name=nick, value=nick)
        for nick in nicks if current.lower() in nick.lower()
    ][:25]

# --- Componentes de UI ---

def get_first_emoji(text: str) -> str:
    """Extrai o primeiro emoji de uma string, ou retorna um placeholder."""
    if not text or not isinstance(text, str):
        return '❓'
    
    emoji_list = emoji.emoji_list(text)
    if not emoji_list:
        return '❓'
        
    return emoji_list[0]['emoji']

class RemoveItemSelect(discord.ui.Select):
    """Menu de seleção para escolher um item a ser removido."""
    def __init__(self, items: list[dict]):
        options = []
        for i, item in enumerate(items):
            brainrot_emoji_text = next((b.get('emoji', '❓') for b in BRAINROTS_DATA if b.get('nome') == item.get('nome')), '❓')
            label = f"{item.get('nome', 'N/A')} ({item.get('cor', 'N/A')})"
            description = f"Quantidade: {item.get('quantidade', 0)}"
            options.append(discord.SelectOption(label=label, description=description, value=str(i), emoji=get_first_emoji(brainrot_emoji_text)))
        
        if not options:
            options.append(discord.SelectOption(label="Nenhum item encontrado", value="-1", default=True))

        super().__init__(placeholder="Selecione um item para remover...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class RemoveQuantityModal(discord.ui.Modal, title="Remover Quantidade de Item"):
    """Formulário para o usuário inserir a quantidade a ser removida."""
    quantity_input = discord.ui.TextInput(
        label="Quantidade a remover",
        placeholder="Digite um número ou 'tudo' para remover o item.",
        style=discord.TextStyle.short,
        required=True,
    )

    def __init__(self, nick_estoque: str, selected_item_index: int, item_info: dict):
        super().__init__()
        self.nick_estoque = nick_estoque
        self.selected_item_index = selected_item_index
        self.item_info = item_info

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        input_value = self.quantity_input.value.lower().strip()
        
        data = ler_contas()
        conta_encontrada = next((c for c in data.get("contas", []) if c["nick"].lower() == self.nick_estoque.lower()), None)

        if not conta_encontrada or len(conta_encontrada.get("brainrots", [])) <= self.selected_item_index:
            await interaction.followup.send("❌ Erro: O item ou a conta não existem mais.", ephemeral=True)
            return
        
        live_item = conta_encontrada["brainrots"][self.selected_item_index]
        quantidade_atual = live_item.get("quantidade", 0)
        
        try:
            if input_value == 'tudo':
                quantidade_a_remover = quantidade_atual
            else:
                quantidade_a_remover = int(input_value)
                if quantidade_a_remover <= 0:
                    await interaction.followup.send("❌ A quantidade deve ser um número positivo.", ephemeral=True)
                    return
                if quantidade_a_remover > quantidade_atual:
                    await interaction.followup.send(f"❌ Você só pode remover até {quantidade_atual} unidades.", ephemeral=True)
                    return
        except ValueError:
            await interaction.followup.send("❌ Entrada inválida. Use um número ou 'tudo'.", ephemeral=True)
            return

        live_item["quantidade"] -= quantidade_a_remover
        
        msg = ""
        if live_item["quantidade"] <= 0:
            conta_encontrada["brainrots"].pop(self.selected_item_index)
            msg = f"✅ Item `{live_item['nome']}` removido completamente do estoque."
        else:
            msg = f"✅ Removido {quantidade_a_remover} de `{live_item['nome']}`. Nova quantidade: {live_item['quantidade']}."

        # Envia a confirmação ANTES de modificar o canal para evitar erros
        await interaction.followup.send(msg, ephemeral=True)
        
        # Atualiza o canal e a mensagem correspondente no Discord
        if interaction.guild:
            await atualizar_canal_da_conta(interaction.guild, conta_encontrada)
            
        salvar_contas(data)


class RemoveItemView(discord.ui.View):
    """View que contém o menu de seleção e o botão de remoção."""
    def __init__(self, nick_estoque: str, items: list[dict]):
        super().__init__(timeout=180)
        self.nick_estoque = nick_estoque
        self.items = items
        self.select_menu = RemoveItemSelect(items)
        self.add_item(self.select_menu)

    @discord.ui.button(label="Remover Quantidade", style=discord.ButtonStyle.danger, row=1)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.select_menu.values or self.select_menu.values[0] == "-1":
            await interaction.response.send_message("Você precisa selecionar um item válido.", ephemeral=True)
            return

        selected_index = int(self.select_menu.values[0])
        item_info = self.items[selected_index]

        modal = RemoveQuantityModal(
            nick_estoque=self.nick_estoque,
            selected_item_index=selected_index,
            item_info=item_info
        )
        await interaction.response.send_modal(modal)

class ConfirmRemoveAccountView(discord.ui.View):
    """View que pede confirmação para remover uma conta de estoque inteira."""
    def __init__(self, nick_estoque: str):
        super().__init__(timeout=60)
        self.nick_estoque = nick_estoque

    @discord.ui.button(label="Sim, remover conta", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = ler_contas()
        
        initial_count = len(data.get("contas", []))
        conta_a_remover = next((c for c in data.get("contas", []) if c["nick"].lower() == self.nick_estoque.lower()), None)
        
        if conta_a_remover:
            data["contas"] = [
                c for c in data.get("contas", []) if c["id"] != conta_a_remover["id"]
            ]
        
        if len(data.get("contas", [])) < initial_count:
            salvar_contas(data)
            # Deleta o canal associado, se houver
            if conta_a_remover:
                channel_id = conta_a_remover.get("discord_channel_id")
                if channel_id and interaction.guild:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.delete(reason="Conta de estoque removida pelo bot.")
                            print(f"[CANAL] Canal '{channel.name}' deletado com sucesso.")
                        except discord.Forbidden:
                            print(f"[ERRO DE PERMISSÃO] Bot sem permissão para deletar o canal '{channel.name}'.")
                        except Exception as e:
                            print(f"[ERRO INESPERADO] Falha ao deletar o canal '{channel.name}': {e}")

            await interaction.edit_original_response(content=f"✅ A conta de estoque `{self.nick_estoque}` e seu canal foram removidos.", view=None)
        else:
            await interaction.edit_original_response(content="❌ A conta não foi encontrada (pode ter sido removida por outra pessoa).", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Operação cancelada.", view=None)

class SearchView(discord.ui.View):
    """View que contém os menus para buscar um item no estoque."""
    def __init__(self):
        super().__init__(timeout=300)

        # Menu para Brainrots (opcional)
        self.brainrot_select = SilentSelect(
            placeholder="Filtrar por Brainrot (opcional)...",
            options=[discord.SelectOption(label=b.get('nome', 'N/A'), value=b.get('nome'), emoji=get_first_emoji(b.get('emoji', '❓'))) for b in BRAINROTS_DATA],
            min_values=0,
            max_values=1
        )
        self.add_item(self.brainrot_select)

        # Menu para Cores (opcional)
        self.cor_select = SilentSelect(
            placeholder="Filtrar por Cor (opcional)...",
            options=[discord.SelectOption(label=c.get('nome', 'N/A'), value=c.get('nome'), emoji=get_first_emoji(c.get('emoji', '❓'))) for c in CORES_DATA],
            min_values=0,
            max_values=1
        )
        self.add_item(self.cor_select)
        
        # Menu para Mutações (opcional)
        self.mutacao_select = SilentSelect(
            placeholder="Filtrar por Mutação (opcional)...",
            options=[discord.SelectOption(label=m.get('nome', 'N/A'), value=m.get('nome'), emoji=get_first_emoji(m.get('emoji', '❓'))) for m in MUTATIONS_DATA],
            min_values=0,
            max_values=1
        )
        self.add_item(self.mutacao_select)

    @discord.ui.button(label="Buscar", style=discord.ButtonStyle.primary, row=4)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        # Pega os valores dos filtros (pode ser None se não selecionado)
        nome_brainrot = self.brainrot_select.values[0] if self.brainrot_select.values else None
        cor = self.cor_select.values[0] if self.cor_select.values else None
        mutacao = self.mutacao_select.values[0] if self.mutacao_select.values else None
        
        if not nome_brainrot and not cor and not mutacao:
            await interaction.edit_original_response(content="❌ Você precisa selecionar pelo menos um filtro para a busca.", view=None)
            return

        data = ler_contas()
        found_items = {}

        for conta in data.get("contas", []):
            matching_items = []
            for item in conta.get("brainrots", []):
                # Filtro por nome
                if nome_brainrot and nome_brainrot != item.get("nome"):
                    continue
                # Filtro por cor
                if cor and cor != item.get("cor"):
                    continue
                # Filtro por mutação
                if mutacao and mutacao not in item.get("mutacoes", []):
                    continue
                
                matching_items.append(item)
            
            if matching_items:
                found_items[conta["nick"]] = matching_items
                
        if not found_items:
            await interaction.edit_original_response(content="ℹ️ Nenhum item correspondente encontrado no estoque.", view=None)
            return

        embed = discord.Embed(title="Resultados da Busca no Estoque", color=EMBED_COLOR)
        for nick, items in found_items.items():
            itens_str = ""
            for item in items:
                brainrot_emoji = get_first_emoji(next((b.get('emoji', '') for b in BRAINROTS_DATA if b['nome'] == item['nome']), ''))
                cor_emoji = get_first_emoji(next((c.get('emoji', '') for c in CORES_DATA if c['nome'] == item['cor']), ''))
                mutacoes_selecionadas = item.get('mutacoes', [])
                mutacoes_emojis = "".join([get_first_emoji(next((m.get('emoji', '') for m in MUTATIONS_DATA if m['nome'] == mut_nome), '')) for mut_nome in mutacoes_selecionadas])
                mutacoes_str = ", ".join(mutacoes_selecionadas) or 'Nenhuma'
                renda_final = calcular_renda(item['nome'], item['cor'], mutacoes_selecionadas)
                itens_str += (f"- {brainrot_emoji} **{item['nome']}** | Qtd: `{item['quantidade']}` | "
                              f"Cor: {cor_emoji} `{item['cor']}` | Mutações: `{mutacoes_emojis} {mutacoes_str}`\n"
                              f"  Renda/s: `${formatar_numero(renda_final)}`\n")
            embed.add_field(name=f"📦 Conta: {nick}", value=itens_str, inline=False)

        await interaction.edit_original_response(content=None, embed=embed, view=None)


class SilentSelect(discord.ui.Select):
    """Um Select que apenas confirma a interação para evitar a mensagem de 'falha'."""
    # Aceita kwargs para passar opções como min_values, max_values, etc.
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        # Esta confirmação é necessária para que o Discord não pense que o bot travou.
        await interaction.response.defer()

class AddBrainrotModal(discord.ui.Modal, title="Definir Quantidade"):
    """Formulário pop-up para o usuário inserir a quantidade de brainrot."""
    quantity_input = discord.ui.TextInput(
        label="Quantidade a ser adicionada",
        placeholder="Digite um número inteiro positivo.",
        style=discord.TextStyle.short,
        required=True,
    )

    def __init__(self, view: 'AddBrainrotView'):
        super().__init__()
        self.add_brainrot_view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            quantidade = int(self.quantity_input.value)
            if quantidade <= 0:
                await interaction.followup.send("❌ A quantidade deve ser um número positivo.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Quantidade inválida. Por favor, insira um número.", ephemeral=True)
            return

        # Coleta os dados selecionados nos menus da View
        nick_estoque = self.add_brainrot_view.nick_estoque
        nome_brainrot = self.add_brainrot_view.brainrot_select.values[0] if self.add_brainrot_view.brainrot_select.values else None
        cor = self.add_brainrot_view.cor_select.values[0] if self.add_brainrot_view.cor_select.values else None
        mutacoes = self.add_brainrot_view.mutacao_select.values
        
        if not nome_brainrot or not cor:
            await interaction.followup.send("❌ Erro: Brainrot ou Cor não foram selecionados corretamente.", ephemeral=True)
            return
        
        data = ler_contas()
        conta_encontrada = next((c for c in data.get("contas", []) if c["nick"].lower() == nick_estoque.lower()), None)

        if not conta_encontrada:
            await interaction.followup.send(f"❌ A conta `{nick_estoque}` não foi encontrada.", ephemeral=True)
            return

        item_encontrado = next((i for i in conta_encontrada["brainrots"] if i["nome"] == nome_brainrot and i["cor"] == cor and sorted(i.get("mutacoes", [])) == sorted(mutacoes)), None)

        if item_encontrado:
            item_encontrado["quantidade"] += quantidade
            msg = f"✅ Quantidade de `{nome_brainrot}` atualizada para {item_encontrado['quantidade']}."
        else:
            novo_item = {"nome": nome_brainrot, "cor": cor, "mutacoes": mutacoes, "quantidade": quantidade}
            conta_encontrada["brainrots"].append(novo_item)
            msg = f"✅ Item `{nome_brainrot}` adicionado com sucesso."

        # Envia a confirmação ANTES de modificar o canal para evitar erros
        await interaction.followup.send(msg, ephemeral=True)

        # Atualiza o canal e a mensagem correspondente no Discord
        if interaction.guild:
            await atualizar_canal_da_conta(interaction.guild, conta_encontrada)

        salvar_contas(data)


class AddLuckyBlockModal(discord.ui.Modal, title="Definir Quantidade"):
    """Formulário pop-up para o usuário inserir a quantidade de Lucky Block."""
    quantity_input = discord.ui.TextInput(
        label="Quantidade a ser adicionada",
        placeholder="Digite um número inteiro positivo.",
        style=discord.TextStyle.short,
        required=True,
    )

    def __init__(self, view: 'AddLuckyBlockView'):
        super().__init__()
        self.add_lucky_block_view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            quantidade = int(self.quantity_input.value)
            if quantidade <= 0:
                await interaction.followup.send("❌ A quantidade deve ser um número positivo.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Quantidade inválida. Por favor, insira um número.", ephemeral=True)
            return

        # Coleta os dados selecionados nos menus da View
        nick_estoque = self.add_lucky_block_view.nick_estoque
        nome_lucky_block = self.add_lucky_block_view.lucky_block_select.values[0] if self.add_lucky_block_view.lucky_block_select.values else None
        
        if not nome_lucky_block:
            await interaction.followup.send("❌ Erro interno: Lucky Block não selecionado.", ephemeral=True)
            return

        # Busca as informações do Lucky Block
        lucky_block_info = next((lb for lb in LUCKY_BLOCKS_DATA if lb['nome'] == nome_lucky_block), None)
        if not lucky_block_info:
            await interaction.followup.send("❌ Lucky Block não encontrado na configuração.", ephemeral=True)
            return

        # Encontra a conta no estoque
        data = ler_contas()
        conta_encontrada = next((c for c in data.get("contas", []) if c["nick"].lower() == nick_estoque.lower()), None)
        
        if not conta_encontrada:
            await interaction.followup.send("❌ Conta não encontrada.", ephemeral=True)
            return

        # Cria o item Lucky Block (sem renda_base, apenas tipo)
        novo_item = {
            "nome": nome_lucky_block,
            "tipo": lucky_block_info.get("tipo"),
            "quantidade": quantidade,
            "is_lucky_block": True  # Flag para identificar que é Lucky Block
        }

        # Adiciona o item à conta
        if "brainrots" not in conta_encontrada:
            conta_encontrada["brainrots"] = []
        
        # Verifica se já existe o mesmo Lucky Block para somar as quantidades
        item_existente = next((item for item in conta_encontrada["brainrots"] 
                              if item.get("nome") == nome_lucky_block and item.get("is_lucky_block", False)), None)
        
        if item_existente:
            item_existente["quantidade"] += quantidade
            msg = f"✅ Adicionado {quantidade}x `{nome_lucky_block}` ao estoque. Nova quantidade: {item_existente['quantidade']}."
        else:
            conta_encontrada["brainrots"].append(novo_item)
            msg = f"✅ Adicionado {quantidade}x `{nome_lucky_block}` ao estoque."

        await interaction.followup.send(msg, ephemeral=True)

        # Atualiza o canal e a mensagem correspondente no Discord
        if interaction.guild:
            await atualizar_canal_da_conta(interaction.guild, conta_encontrada)

        salvar_contas(data)


class ItemTypeSelect(discord.ui.Select):
    def __init__(self, nick_estoque: str):
        self.nick_estoque = nick_estoque
        options = [
            discord.SelectOption(label="Brainrot", description="Adicionar um item com renda.", emoji="🧠"),
            discord.SelectOption(label="Lucky Block", description="Adicionar uma caixa surpresa .", emoji="📦"),
            discord.SelectOption(label="Rebirth", description="Adicionar conta para dar rebirth.", emoji="🔄")
        ]
        super().__init__(placeholder="Selecione o tipo de item para adicionar...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        if selected_type == "Brainrot":
            view = AddBrainrotView(nick_estoque=self.nick_estoque)
            await interaction.response.edit_message(content=f"Adicionando **Brainrot** para **{self.nick_estoque}**:", view=view)
        elif selected_type == "Lucky Block":
            view = AddLuckyBlockView(nick_estoque=self.nick_estoque)
            await interaction.response.edit_message(content=f"Adicionando **Lucky Block** para **{self.nick_estoque}**:", view=view)
        elif selected_type == "Rebirth":
            await self.processar_conta_rebirth(interaction)

    async def processar_conta_rebirth(self, interaction: discord.Interaction):
        """Processa a adição de uma conta rebirth."""
        nick_estoque = self.nick_estoque
        
        # Primeiro, busca a conta nas contas normais
        data = ler_contas()
        conta_encontrada = next((c for c in data.get("contas", []) if c["nick"].lower() == nick_estoque.lower()), None)
        
        if not conta_encontrada:
            await interaction.response.edit_message(
                content=f"❌ Conta `{nick_estoque}` não encontrada no estoque normal.",
                view=None
            )
            return
        
        # Verifica se a conta já está no rebirth
        data_rebirth = ler_contas_rebirth()
        conta_rebirth_existente = next((c for c in data_rebirth.get("contas_rebirth", []) if c["nick"].lower() == nick_estoque.lower()), None)
        
        if conta_rebirth_existente:
            await interaction.response.edit_message(
                content=f"❌ A conta `{nick_estoque}` já está no sistema de rebirth.",
                view=None
            )
            return
        
        # Move a conta para o sistema rebirth
        conta_rebirth = {
            "id": max([c.get("id", 0) for c in data_rebirth.get("contas_rebirth", [])] + [0]) + 1,
            "nick": conta_encontrada["nick"],
            "senha": conta_encontrada["senha"],
            "email": conta_encontrada["email"],
            "tipo": "rebirth"
        }
        
        # Adiciona à lista de contas rebirth
        data_rebirth.get("contas_rebirth", []).append(conta_rebirth)
        salvar_contas_rebirth(data_rebirth)
        
        # Remove da lista de contas normais
        contas_atualizadas = [c for c in data.get("contas", []) if c.get("id") != conta_encontrada.get("id")]
        data["contas"] = contas_atualizadas
        salvar_contas(data)
        
        # Se existir canal Discord, agenda sua deleção
        if conta_encontrada.get("discord_channel_id"):
            adicionar_tarefa("deletar_canal", {"channel_id": conta_encontrada["discord_channel_id"]})
        
        # Cria novo canal Discord para a conta rebirth
        if interaction.guild:
            await atualizar_canal_conta_rebirth(interaction.guild, conta_rebirth)
            # Salva novamente para incluir os IDs do canal e mensagem
            data_rebirth["contas_rebirth"] = [c if c.get("id") != conta_rebirth["id"] else conta_rebirth for c in data_rebirth.get("contas_rebirth", [])]
            salvar_contas_rebirth(data_rebirth)
        
        await interaction.response.edit_message(
            content=f"✅ Conta `{nick_estoque}` movida para o sistema de **Rebirth**!\n"
                   f"🔄 Agora ela pode ser usada para vendas de rebirth.\n"
                   f"📺 Canal Discord criado automaticamente.",
            view=None
        )

class ItemTypeSelectView(discord.ui.View):
    """View inicial para selecionar entre Brainrot ou Lucky Block usando um dropdown."""
    def __init__(self, nick_estoque: str):
        super().__init__(timeout=300)
        self.add_item(ItemTypeSelect(nick_estoque))

class AddBrainrotView(discord.ui.View):
    """View que contém os menus para adicionar um brainrot."""
    def __init__(self, nick_estoque: str):
        super().__init__(timeout=300)
        self.nick_estoque = nick_estoque

        # Menu para Brainrots
        self.brainrot_select = SilentSelect(
            placeholder="1. Selecione o Brainrot...",
            options=[discord.SelectOption(label=b.get('nome', 'N/A'), value=b.get('nome'), emoji=get_first_emoji(b.get('emoji', '❓'))) for b in BRAINROTS_DATA]
        )
        self.add_item(self.brainrot_select)

        # Menu para Cores
        self.cor_select = SilentSelect(
            placeholder="2. Selecione a Cor...",
            options=[discord.SelectOption(label=c.get('nome', 'N/A'), value=c.get('nome'), emoji=get_first_emoji(c.get('emoji', '❓'))) for c in CORES_DATA]
        )
        self.add_item(self.cor_select)
        
        # Menu para Mutações (multi-seleção)
        self.mutacao_select = SilentSelect(
            placeholder="3. Selecione as Mutações...",
            min_values=0,
            max_values=len(MUTATIONS_DATA),
            options=[discord.SelectOption(label=m.get('nome', 'N/A'), value=m.get('nome'), emoji=get_first_emoji(m.get('emoji', '❓'))) for m in MUTATIONS_DATA]
        )
        self.add_item(self.mutacao_select)

    @discord.ui.button(label="4. Definir Quantidade e Adicionar", style=discord.ButtonStyle.success, row=4)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validação: Garante que os menus de escolha única foram selecionados
        if not self.brainrot_select.values or not self.cor_select.values:
            await interaction.response.send_message("Você precisa selecionar um Brainrot e uma Cor.", ephemeral=True, delete_after=10)
            return

        modal = AddBrainrotModal(view=self)
        await interaction.response.send_modal(modal)


class AddLuckyBlockView(discord.ui.View):
    """View que contém o menu para adicionar um Lucky Block."""
    def __init__(self, nick_estoque: str):
        super().__init__(timeout=300)
        self.nick_estoque = nick_estoque

        # Menu para Lucky Blocks
        self.lucky_block_select = SilentSelect(
            placeholder="1. Selecione o Lucky Block...",
            options=[discord.SelectOption(label=lb.get('nome', 'N/A'), value=lb.get('nome'), emoji=get_first_emoji(lb.get('emoji', '❓'))) for lb in LUCKY_BLOCKS_DATA]
        )
        self.add_item(self.lucky_block_select)

    @discord.ui.button(label="2. Definir Quantidade e Adicionar", style=discord.ButtonStyle.success, row=4)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validação: Garante que o Lucky Block foi selecionado
        if not self.lucky_block_select.values:
            await interaction.response.send_message("Você precisa selecionar um Lucky Block.", ephemeral=True, delete_after=10)
            return

        modal = AddLuckyBlockModal(view=self)
        await interaction.response.send_modal(modal)

# --- Funções de Cálculo ---

def formatar_numero(n, for_channel_name=False):
    """Formata números grandes para uma leitura mais fácil (ex: 1.5B, 250M, 120K)."""
    if n >= 1_000_000_000:
        text = f"{n / 1_000_000_000:.2f}B".replace(".00", "")
    elif n >= 1_000_000:
        text = f"{n / 1_000_000:.2f}M".replace(".00", "")
    elif n >= 1_000:
        text = f"{n / 1_000:.2f}K".replace(".00", "")
    else:
        text = str(n)
    
    if for_channel_name:
        return text.replace('.', 'ˌ')
    return text

def calcular_renda(nome_brainrot, nome_cor, nomes_mutacoes: list):
    renda_base = next((b.get('renda_base', 0) for b in BRAINROTS_DATA if b['nome'] == nome_brainrot), 0)
    mult_cor = next((c.get('multiplicador', 1) for c in CORES_DATA if c['nome'] == nome_cor), 1)
    
    mult_mutacao_total = 1.0
    for nome_mut in nomes_mutacoes:
        mult_mutacao_individual = next((m.get('multiplicador', 1) for m in MUTATIONS_DATA if m['nome'] == nome_mut), 1)
        mult_mutacao_total *= mult_mutacao_individual
        
    return renda_base * mult_cor * mult_mutacao_total

def calcular_renda_brainrot(nome_brainrot, cor, mutacoes):
    """Calcula a renda de um brainrot específico."""
    return calcular_renda(nome_brainrot, cor, mutacoes)

# --- Funções de Organização de Canais ---

def criar_embed_conta(conta: dict) -> discord.Embed:
    """Cria um embed com os detalhes completos de uma conta de estoque."""
    embed = discord.Embed(
        title="📦 Detalhes da Conta",
        color=EMBED_COLOR
    )

    # Organiza as credenciais em campos inline para um layout mais compacto
    embed.add_field(name="👤 Nick", value=f"`{conta['nick']}`", inline=True)
    embed.add_field(name="📧 Email", value=f"`{conta.get('email', 'N/A')}`", inline=True)
    embed.add_field(name="🔑 Senha", value=f"`{conta.get('senha', 'N/A')}`", inline=True)

    itens_na_conta = conta.get('brainrots', [])
    total_quantidade_geral = 0
    renda_total_conta = 0

    if not itens_na_conta:
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="🛒 Itens na Conta:", value="_Esta conta de estoque está vazia._", inline=False)
    else:
        # Adiciona um título para a seção de itens, quebrando a linha dos campos inline.
        embed.add_field(name="🛒 Itens na Conta:", value="\u200b", inline=False)
        for item in itens_na_conta:
            # Coleta de dados do item
            nome_item = item['nome']
            quantidade = item.get('quantidade', 0)
            total_quantidade_geral += quantidade

            # Verifica se é um Lucky Block
            if item.get('is_lucky_block', False):
                # Lucky Block - busca emoji e tipo
                lucky_block_info = next((lb for lb in LUCKY_BLOCKS_DATA if lb.get('nome') == nome_item), {})
                item_emoji_text = lucky_block_info.get('emoji', '📦')
                tipo = item.get('tipo', 'Unknown')
                
                field_value_lines = [
                    f"> **Quantidade:** `{quantidade}`",
                    f"> **Tipo:** `{tipo}`",
                    f"> **Renda Individual:** `N/A (Lucky Block)`"
                ]
                
                field_value = "\n".join(field_value_lines)
                
                # Adiciona campo para Lucky Block
                embed.add_field(
                    name=f"{get_first_emoji(item_emoji_text)} {nome_item}",
                    value=field_value,
                    inline=False
                )
            else:
                # Brainrot normal - lógica existente
                cor = item['cor']
                mutacoes = item.get('mutacoes', [])

                # Busca de emojis e formatação de texto
                brainrot_emoji_text = next((b.get('emoji', '❓') for b in BRAINROTS_DATA if b.get('nome') == nome_item), '❓')
                cor_emoji_text = next((c.get('emoji', '⚪') for c in CORES_DATA if c.get('nome') == cor), '⚪')
                mutacoes_selecionadas = item.get('mutacoes', [])
                mutacoes_emojis_text = [next((m.get('emoji', '') for m in MUTATIONS_DATA if m['nome'] == mut_nome), '') for mut_nome in mutacoes_selecionadas]
                mutacoes_emojis_str = "".join([get_first_emoji(e) for e in mutacoes_emojis_text if e])
                
                # Cálculos de renda
                renda_individual = calcular_renda_brainrot(nome_item, cor, mutacoes)
                renda_total_item = renda_individual * quantidade
                renda_total_conta += renda_total_item

                # Construção do valor do campo para este item
                field_value_lines = [
                    f"> **Quantidade:** `{quantidade}`",
                    f"> **Cor:** {get_first_emoji(cor_emoji_text)} `{cor}`"
                ]

                if mutacoes_selecionadas:
                    mutacoes_str = ", ".join(mutacoes_selecionadas)
                    field_value_lines.append(f"> **Mutações:** `{mutacoes_emojis_str} {mutacoes_str}`")
                
                field_value_lines.append(f"> **Renda Individual:** `${formatar_numero(renda_individual)}/s`")
                
                field_value = "\n".join(field_value_lines)

                # Adiciona um campo para cada tipo de item
                embed.add_field(
                        name=f"{get_first_emoji(brainrot_emoji_text)} {nome_item}",
                    value=field_value,
                    inline=False
                )
        
        # --- Bloco de Resumo ---
        
        # Adiciona um separador para o resumo
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        summary_value = (
            f"> **Total de Itens na Conta:** `{total_quantidade_geral}`\n"
            f"> **Renda Total da Conta:** `${formatar_numero(renda_total_conta)}/s`"
        )
        embed.add_field(name="📈 Resumo da Conta", value=summary_value, inline=False)

    embed.set_footer(text=f"ID da Conta: {conta.get('id', 'N/A')}")
    return embed


class ManageAccountView(discord.ui.View):
    """View persistente com botões para gerenciar uma conta."""
    def __init__(self):
        super().__init__(timeout=None) # Garante que a view seja persistente

    async def find_conta_from_interaction(self, interaction: discord.Interaction) -> dict | None:
        """Encontra a conta correspondente ao canal da interação (específica, mista ou rebirth)."""
        # Primeiro, tenta encontrar em contas específicas
        data = ler_contas()
        conta_encontrada = next((c for c in data.get("contas", []) if c.get("discord_channel_id") == interaction.channel_id), None)
        
        if conta_encontrada:
            conta_encontrada["_tipo"] = "especifica"  # Marca o tipo para uso posterior
            return conta_encontrada
        
        # Se não encontrou, tenta em contas mistas
        data_mistas = ler_contas_mistas()
        conta_mista = next((c for c in data_mistas.get("contas_mistas", []) if c.get("discord_channel_id") == interaction.channel_id), None)
        
        if conta_mista:
            conta_mista["_tipo"] = "mista"  # Marca o tipo para uso posterior
            return conta_mista
        
        # Se não encontrou, tenta em contas rebirth
        data_rebirth = ler_contas_rebirth()
        conta_rebirth = next((c for c in data_rebirth.get("contas_rebirth", []) if c.get("discord_channel_id") == interaction.channel_id), None)
        
        if conta_rebirth:
            conta_rebirth["_tipo"] = "rebirth"  # Marca o tipo para uso posterior
            return conta_rebirth
            
        await interaction.response.send_message("❌ Não foi possível encontrar a conta associada a este canal. Talvez ela tenha sido removida.", ephemeral=True, delete_after=10)
        return None

    @discord.ui.button(label="Adicionar Item", style=discord.ButtonStyle.success, emoji="➕", custom_id="manage_account:add_item")
    async def add_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conta = await self.find_conta_from_interaction(interaction)
        if not conta:
            return
        
        # Verifica se é uma conta mista
        if conta.get("_tipo") == "mista":
            await interaction.response.send_message(
                "ℹ️ **Esta é uma conta mista** - ela já contém brainrots pré-definidos conforme a faixa configurada.\n"
                "Para modificar contas mistas, use os comandos `/remove` ou `/add conta_mista`.", 
                ephemeral=True
            )
            return
        
        # Verifica se é uma conta rebirth
        if conta.get("_tipo") == "rebirth":
            await interaction.response.send_message(
                "ℹ️ **Esta é uma conta rebirth** - ela não precisa de itens adicionais.\n"
                "Contas rebirth são usadas diretamente para vendas de rebirth.\n"
                "Use `/remove conta` se quiser remover esta conta do sistema.", 
                ephemeral=True
            )
            return
        
        view = ItemTypeSelectView(nick_estoque=conta["nick"])
        await interaction.response.send_message(f"Selecione o tipo de item para **{conta['nick']}**:", view=view, ephemeral=True)

    @discord.ui.button(label="Remover Item", style=discord.ButtonStyle.primary, emoji="➖", custom_id="manage_account:remove_item")
    async def remove_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conta = await self.find_conta_from_interaction(interaction)
        if not conta:
            return
        
        # Verifica se é uma conta mista
        if conta.get("_tipo") == "mista":
            await interaction.response.send_message(
                "ℹ️ **Esta é uma conta mista** - ela já contém brainrots pré-definidos conforme a faixa configurada.\n"
                "Para remover contas mistas, use o comando `/remove conta` especificando o nick.", 
                ephemeral=True
            )
            return
        
        # Verifica se é uma conta rebirth
        if conta.get("_tipo") == "rebirth":
            await interaction.response.send_message(
                "ℹ️ **Esta é uma conta rebirth** - ela não possui itens individuais para remover.\n"
                "Use `/remove conta` se quiser remover esta conta inteira do sistema.", 
                ephemeral=True
            )
            return
        
        if not conta.get("brainrots"):
            await interaction.response.send_message(f"ℹ️ A conta `{conta['nick']}` não possui itens para remover.", ephemeral=True)
            return

        view = RemoveItemView(nick_estoque=conta["nick"], items=conta["brainrots"])
        await interaction.response.send_message("Selecione o item que deseja remover:", view=view, ephemeral=True)


def get_renda_tier(renda_total: int) -> dict | None:
    """Encontra a faixa de renda correspondente."""
    for tier in RENDA_TIERS_DATA:
        if tier["min"] <= renda_total <= tier["max"]:
            return tier
    return None

def slugify(text: str) -> str:
    """Converte uma string para um formato de nome de canal do Discord."""
    text = text.lower().replace(" ", "-")
    return "".join(c for c in text if c.isalnum() or c == "-")

async def atualizar_canal_da_conta(guild: discord.Guild, conta: dict):
    """Cria ou atualiza o canal e a mensagem de status de uma conta no Discord."""
    nick = conta.get("nick", "conta-desconhecida")
    itens = conta.get("brainrots", [])
    channel_id = conta.get("discord_channel_id")
    
    # --- 1. Determinar o estado desejado (Categoria e Nome do Canal) ---
    is_pure = len(itens) == 1 and not itens[0].get("mutacoes") if itens else False
    is_lucky_block_only = len(itens) == 1 and itens[0].get("is_lucky_block", False) if itens else False
    
    desired_category_name = ""
    desired_channel_name = ""
    desired_channel_topic = ""

    if is_lucky_block_only:
        # Conta pura com apenas Lucky Block
        item = itens[0]
        lucky_block_nome = item["nome"]
        tipo = item.get("tipo", "Unknown")
        
        lucky_block_info = next((lb for lb in LUCKY_BLOCKS_DATA if lb.get('nome') == lucky_block_nome), {})
        canal_emoji = lucky_block_info.get('canal_emoji', '📦🪽')
        
        desired_category_name = f"Lucky Block {tipo}"
        desired_channel_name = f"〔{canal_emoji}〕{slugify(nick)}"
        desired_channel_topic = f"Conta pura com {lucky_block_nome} ({tipo})."
    
    elif is_pure:
        # Conta pura com brainrot normal
        item = itens[0]
        brainrot_nome = item["nome"]
        cor_nome = item["cor"]
        
        brainrot_info = next((b for b in BRAINROTS_DATA if b.get('nome') == brainrot_nome), {})
        cor_info = next((c for c in CORES_DATA if c.get('nome') == cor_nome), {})
        
        brainrot_emoji = get_first_emoji(brainrot_info.get('emoji', '❓'))
        cor_emoji = get_first_emoji(cor_info.get('emoji', '⚪'))

        desired_category_name = brainrot_nome
        desired_channel_name = f"〔{brainrot_emoji}・{cor_emoji}〕{slugify(nick)}"
        desired_channel_topic = f"Conta pura com {brainrot_nome} ({cor_nome})."
    
    else: # Conta Mista (ou vazia)
        # Calcula renda total apenas para brainrots (Lucky Blocks não têm renda)
        renda_total = sum(calcular_renda(i['nome'], i['cor'], i.get('mutacoes', [])) * i.get('quantidade', 1) 
                         for i in itens if not i.get('is_lucky_block', False))
        
        desired_category_name = "Contas Mistas"
        
        # Nome do canal para contas mistas agora inclui a renda
        renda_formatada = formatar_numero(renda_total, for_channel_name=True)
        desired_channel_name = f"〔${renda_formatada}〕{slugify(nick)}"

        if not itens:
            desired_channel_topic = "Esta conta está vazia."
        else:
            tier = get_renda_tier(renda_total)
            if tier:
                # Tópico do canal agora contém a informação de renda
                desired_channel_topic = f"Faixa: {tier.get('nome_faixa')} | Renda Total: ${formatar_numero(renda_total)}/s"
            else:
                # Tópico padrão para contas mistas sem tier
                desired_channel_topic = "Renda total não se encaixa em nenhuma faixa."


    # --- 2. Preparar Embed e View ---
    embed = criar_embed_conta(conta)
    view = ManageAccountView()
    
    try:
        channel_id = conta.get("discord_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None

        # Garante que a categoria de destino exista
        target_category = discord.utils.get(guild.categories, name=desired_category_name)
        if not target_category:
            target_category = await guild.create_category(name=desired_category_name)
        
        # --- 3. Lógica de Recriação vs. Atualização ---
        # Para evitar rate limits, o canal é recriado se o nome ou a categoria mudarem.

        should_recreate = False
        if not channel or not isinstance(channel, discord.TextChannel):
            should_recreate = True # Canal não existe, precisa ser criado
        elif channel.name != desired_channel_name or channel.category_id != target_category.id:
            should_recreate = True # Canal precisa ser renomeado ou movido, então recriamos

        if should_recreate:
            # Se o canal antigo existe, deleta primeiro
            if channel:
                try:
                    await channel.delete(reason="Recriando canal com informações atualizadas.")
                    print(f"[CANAL] Canal antigo '{channel.name}' deletado para recriação.")
                except (discord.Forbidden, discord.NotFound) as e:
                    print(f"[AVISO] Não foi possível deletar o canal antigo '{channel.name}': {e}")
            
            # Cria o novo canal
            new_channel = await guild.create_text_channel(
                name=desired_channel_name, 
                category=target_category, 
                topic=desired_channel_topic
            )
            new_message = await new_channel.send(embed=embed, view=view)
            
            # Atualiza os IDs na conta
            conta["discord_channel_id"] = new_channel.id
            conta["discord_message_id"] = new_message.id
            print(f"[CANAL] Canal '{desired_channel_name}' recriado para a conta '{nick}'.")

        else: # O canal já existe e não precisa ser recriado
            # Garante que estamos lidando com um canal de texto antes de prosseguir
            if isinstance(channel, discord.TextChannel):
                # Apenas atualiza o tópico se necessário
                if channel.topic != desired_channel_topic:
                    await channel.edit(topic=desired_channel_topic)
                
                # E atualiza a mensagem
                message_id = conta.get("discord_message_id")
                if message_id:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(embed=embed, view=view)
                    except discord.NotFound:
                        new_message = await channel.send(embed=embed, view=view)
                        conta["discord_message_id"] = new_message.id
                else:
                    new_message = await channel.send(embed=embed, view=view)
                    conta["discord_message_id"] = new_message.id

    except discord.Forbidden:
        print(f"[ERRO DE PERMISSÃO] O bot não tem permissão para gerenciar canais/mensagens no servidor '{guild.name}'.")
    except Exception as e:
        print(f"[ERRO INESPERADO] Falha ao atualizar canal para a conta {nick}: {e}")

async def atualizar_canal_conta_mista(guild: discord.Guild, conta_mista: dict):
    """Cria ou atualiza o canal de uma conta mista no Discord."""
    nick = conta_mista.get("nick", "conta-mista-desconhecida")
    produto = conta_mista.get("produto_misto", {})
    faixa = produto.get("faixa", "Faixa Desconhecida")
    quantidade = produto.get("quantidade", 0)
    channel_id = conta_mista.get("discord_channel_id")
    
    # Nome e configuração do canal para conta mista
    desired_category_name = "Contas Mistas"
    faixa_formatada = faixa.lower().replace('-', '˗')  # Usa hífen especial
    desired_channel_name = f"〔🎁〕{slugify(nick)}「{faixa_formatada}」"
    desired_channel_topic = f"Conta mista: {quantidade}x brainrots ({faixa})"
    
    # Embed específico para conta mista
    embed = discord.Embed(
        title="🎁 Conta Mista",
        color=0x3498db
    )
    
    embed.add_field(name="👤 Nick", value=f"`{conta_mista['nick']}`", inline=True)
    embed.add_field(name="📧 Email", value=f"`{conta_mista.get('email', 'N/A')}`", inline=True)
    embed.add_field(name="🔑 Senha", value=f"`{conta_mista.get('senha', 'N/A')}`", inline=True)
    
    embed.add_field(name="🎯 Faixa de Renda", value=f"`{faixa}`", inline=True)
    embed.add_field(name="🔢 Quantidade", value=f"`{quantidade} brainrots`", inline=True)
    embed.add_field(name="💰 Tipo", value="`Produtos Mistos`", inline=True)
    
    # View para gerenciamento (pode ser adaptada depois)
    view = ManageAccountView()
    
    try:
        channel = guild.get_channel(channel_id) if channel_id else None

        # Garante que a categoria de destino exista
        target_category = discord.utils.get(guild.categories, name=desired_category_name)
        if not target_category:
            target_category = await guild.create_category(name=desired_category_name)
        
        should_recreate = False
        if not channel or not isinstance(channel, discord.TextChannel):
            should_recreate = True
        elif channel.name != desired_channel_name or channel.category_id != target_category.id:
            should_recreate = True

        if should_recreate:
            # Deleta canal antigo se existir
            if channel:
                try:
                    await channel.delete(reason="Recriando canal de conta mista.")
                    print(f"[CANAL MISTO] Canal antigo '{channel.name}' deletado para recriação.")
                except (discord.Forbidden, discord.NotFound) as e:
                    print(f"[AVISO] Não foi possível deletar o canal antigo '{channel.name}': {e}")
            
            # Cria novo canal
            new_channel = await guild.create_text_channel(
                name=desired_channel_name, 
                category=target_category, 
                topic=desired_channel_topic
            )
            new_message = await new_channel.send(embed=embed, view=view)
            
            # Atualiza os IDs na conta mista
            conta_mista["discord_channel_id"] = new_channel.id
            conta_mista["discord_message_id"] = new_message.id
            print(f"[CANAL MISTO] Canal '{desired_channel_name}' criado para a conta mista '{nick}'.")

        else:
            # Atualiza canal existente
            if isinstance(channel, discord.TextChannel):
                if channel.topic != desired_channel_topic:
                    await channel.edit(topic=desired_channel_topic)
                
                message_id = conta_mista.get("discord_message_id")
                if message_id:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(embed=embed, view=view)
                    except discord.NotFound:
                        new_message = await channel.send(embed=embed, view=view)
                        conta_mista["discord_message_id"] = new_message.id
                else:
                    new_message = await channel.send(embed=embed, view=view)
                    conta_mista["discord_message_id"] = new_message.id

    except discord.Forbidden:
        print(f"[ERRO DE PERMISSÃO] O bot não tem permissão para gerenciar canais no servidor '{guild.name}'.")
    except Exception as e:
        print(f"[ERRO INESPERADO] Falha ao atualizar canal para a conta mista {nick}: {e}")

async def atualizar_canal_conta_rebirth(guild: discord.Guild, conta_rebirth: dict):
    """Cria ou atualiza o canal de uma conta rebirth no Discord."""
    nick = conta_rebirth.get("nick", "conta-rebirth-desconhecida")
    channel_id = conta_rebirth.get("discord_channel_id")
    
    # Nome e configuração do canal para conta rebirth
    desired_category_name = "Contas Rebirth"
    desired_channel_name = f"〔🔄〕{slugify(nick)}"
    desired_channel_topic = f"Conta para rebirth - Nick: {nick}"
    
    # Embed específico para conta rebirth
    embed = discord.Embed(
        title="🔄 Conta Rebirth",
        color=0x3498db
    )
    
    embed.add_field(name="👤 Nick", value=f"`{conta_rebirth['nick']}`", inline=True)
    embed.add_field(name="📧 Email", value=f"`{conta_rebirth.get('email', 'N/A')}`", inline=True)
    embed.add_field(name="🔑 Senha", value=f"`{conta_rebirth.get('senha', 'N/A')}`", inline=True)
    
    # View sem botões para contas rebirth
    view = discord.ui.View(timeout=None)
    
    try:
        channel = guild.get_channel(channel_id) if channel_id else None

        # Garante que a categoria de destino exista
        target_category = discord.utils.get(guild.categories, name=desired_category_name)
        if not target_category:
            target_category = await guild.create_category(name=desired_category_name)
        
        should_recreate = False
        if not channel or not isinstance(channel, discord.TextChannel):
            should_recreate = True
        elif channel.name != desired_channel_name or channel.category_id != target_category.id:
            should_recreate = True

        if should_recreate:
            # Deleta canal antigo se existir
            if channel:
                try:
                    await channel.delete(reason="Recriando canal de conta rebirth.")
                    print(f"[CANAL REBIRTH] Canal antigo '{channel.name}' deletado para recriação.")
                except (discord.Forbidden, discord.NotFound) as e:
                    print(f"[AVISO] Não foi possível deletar o canal antigo '{channel.name}': {e}")
            
            # Cria novo canal
            new_channel = await guild.create_text_channel(
                name=desired_channel_name, 
                category=target_category, 
                topic=desired_channel_topic
            )
            new_message = await new_channel.send(embed=embed, view=view)
            
            # Atualiza os IDs na conta rebirth
            conta_rebirth["discord_channel_id"] = new_channel.id
            conta_rebirth["discord_message_id"] = new_message.id
            print(f"[CANAL REBIRTH] Canal '{desired_channel_name}' criado para a conta rebirth '{nick}'.")

        else:
            # Atualiza canal existente
            if isinstance(channel, discord.TextChannel):
                if channel.topic != desired_channel_topic:
                    await channel.edit(topic=desired_channel_topic)
                
                message_id = conta_rebirth.get("discord_message_id")
                if message_id:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(embed=embed, view=view)
                    except discord.NotFound:
                        new_message = await channel.send(embed=embed, view=view)
                        conta_rebirth["discord_message_id"] = new_message.id
                else:
                    new_message = await channel.send(embed=embed, view=view)
                    conta_rebirth["discord_message_id"] = new_message.id

    except discord.Forbidden:
        print(f"[ERRO DE PERMISSÃO] O bot não tem permissão para gerenciar canais no servidor '{guild.name}'.")
    except Exception as e:
        print(f"[ERRO INESPERADO] Falha ao atualizar canal para a conta rebirth {nick}: {e}")

# --- Novo Processador de Tarefas ---

async def processar_tarefas_pendentes(client: discord.Client):
    """Verifica e processa tarefas da fila tarefas.json."""
    tarefas_data = ler_tarefas()
    tarefas_pendentes = tarefas_data.get("tarefas", [])

    if not tarefas_pendentes:
        return # Nenhuma tarefa a fazer

    print(f"[TAREFAS] Encontradas {len(tarefas_pendentes)} tarefas pendentes. Processando...")

    tarefas_restantes = []
    for tarefa in tarefas_pendentes:
        tipo = tarefa.get("tipo")
        dados = tarefa.get("dados")
        
        try:
            if tipo == "deletar_canal":
                channel_id = dados.get("channel_id")
                if channel_id:
                    # Usamos o client para encontrar o canal em qualquer servidor que o bot esteja
                    channel = client.get_channel(channel_id)
                    if channel:
                        canal_nome = channel.name
                        await channel.delete(reason="Canal de conta vendida deletado pelo gerenciador.")
                        print(f"[TAREFAS] ✅ Canal '{canal_nome}' (ID: {channel_id}) deletado com sucesso.")
                    else:
                        print(f"[TAREFAS] ⚠️ Aviso: Canal {channel_id} não encontrado. Pode já ter sido deletado.")
                else:
                    print("[TAREFAS] ❌ Erro: Tarefa 'deletar_canal' sem 'channel_id'.")
            
            # Se a tarefa foi processada com sucesso (ou era inválida), ela não é adicionada
            # à lista de tarefas restantes.
            
        except discord.Forbidden:
            print(f"[TAREFAS] ❌ Erro de permissão ao tentar deletar o canal {dados.get('channel_id')}. A tarefa será mantida para nova tentativa.")
            tarefas_restantes.append(tarefa) # Mantém a tarefa na fila se houver erro de permissão
        except Exception as e:
            print(f"[TAREFAS] ❌ Erro inesperado ao processar tarefa '{tipo}': {e}")
            # Dependendo do erro, você pode decidir se quer manter a tarefa ou não.
            # Por segurança, vamos mantê-la por enquanto.
            tarefas_restantes.append(tarefa)

    # Salva apenas as tarefas que falharam em serem processadas
    tarefas_data["tarefas"] = tarefas_restantes
    salvar_tarefas(tarefas_data)


# --- Funções do Sistema de Vendas GGMAX ---

async def renovar_access_token():
    """Renova o token de acesso da API da GGMAX."""
    global GGMAX_TOKEN, GGMAX_TOKEN_EXP
    
    refresh_token = CONFIG_DATA.get("GGMAX_REFRESH_TOKEN")
    if not refresh_token:
        print("[GGMAX] Token de refresh não encontrado no config.json")
        return False
    
    url = "https://ggmax.com.br/api/auth/refresh-token"
    payload = {"refresh_token": refresh_token}
    headers = {"Content-Type": "application/json"}
    
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.post(url, json=payload, headers=headers)
        if resp.status_code == 200 and resp.json().get("success"):
            GGMAX_TOKEN = resp.json()["data"]["token"]
            payload_part = GGMAX_TOKEN.split(".")[1]
            payload_part += '=' * (-len(payload_part) % 4)
            GGMAX_TOKEN_EXP = json.loads(base64.urlsafe_b64decode(payload_part)).get("exp", 0)
            print(f"[GGMAX] ✅ Token de acesso renovado!")
            return True
        print(f"[GGMAX] ❌ Falha ao renovar token: {resp.status_code}")
        return False
    except Exception as e:
        print(f"[GGMAX] ❌ Erro ao renovar token: {e}")
        return False

async def token_esta_expirando():
    """Verifica se o token precisa ser renovado."""
    return GGMAX_TOKEN is None or (GGMAX_TOKEN_EXP - time.time() < 120)

async def enviar_mensagem_ggmax(order_code, mensagem):
    """Envia uma mensagem para o chat de um pedido na GGMAX."""
    if await token_esta_expirando():
        if not await renovar_access_token():
            return False
    
    url = f"https://ggmax.com.br/api/orders/{order_code}/chat-items"
    payload = {"temp_id": str(int(time.time() * 1000)), "content": mensagem}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GGMAX_TOKEN}"}
    
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, json=payload, headers=headers)
        print(f"[GGMAX API] Envio mensagem - Status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"[GGMAX API] Erro ao enviar mensagem: {e}")
        return False

async def marcar_pedido_entregue(order_code):
    """Marca um pedido como entregue na GGMAX."""
    if await token_esta_expirando():
        if not await renovar_access_token():
            return False
    
    url = f"https://ggmax.com.br/api/orders/{order_code}/mark-as-delivered"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GGMAX_TOKEN}"}
    
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, headers=headers)
        print(f"[GGMAX API] Marcar entregue - Status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"[GGMAX API] Erro ao marcar como entregue: {e}")
        return False

async def avaliar_cliente(order_code):
    """Avalia o cliente positivamente na GGMAX."""
    if await token_esta_expirando():
        if not await renovar_access_token():
            return False
    
    url = f"https://ggmax.com.br/api/orders/{order_code}/user-reviews"
    payload = {
        "message": "🌟 Cliente nota 10! Obrigado por escolher a Porkin Store para seus Brainrots. Espero te atender novamente! 😄 ",
        "review_type": "positive"
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GGMAX_TOKEN}"}
    
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, json=payload, headers=headers)
        print(f"[GGMAX API] Avaliar cliente - Status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"[GGMAX API] Erro ao avaliar cliente: {e}")
        return False

async def entregar_conta_especifica(codigo_pedido, item_nome_ggmax, cor_item, quantidade_total):
    """
    Processa a entrega de uma conta específica para a GGMAX, usando busca por similaridade de nome.
    """
    print(f"[ENTREGA] 🔍 Processando pedido {codigo_pedido} para '{item_nome_ggmax}' ({cor_item}) x{quantidade_total}...")
    
    data = ler_contas()
    contas = data.get("contas", [])
    
    # 1. Encontrar o nome mais próximo no nosso sistema
    nomes_disponiveis = {b['nome'] for b in BRAINROTS_DATA}
    matches = difflib.get_close_matches(item_nome_ggmax, nomes_disponiveis, n=1, cutoff=0.8)
    
    nome_item_sistema = None
    if matches:
        nome_item_sistema = matches[0]
        if nome_item_sistema.lower() != item_nome_ggmax.lower():
            print(f"[ENTREGA] ⚠️ Nome correspondido por similaridade: '{item_nome_ggmax}' -> '{nome_item_sistema}'")
    else:
        print(f"[ENTREGA] ❌ Não foi encontrado um nome de item similar a '{item_nome_ggmax}' no sistema.")
        return

    # 2. Buscar conta que corresponde ao item e quantidade
    conta_para_entregar = None
    for conta in contas:
        for item in conta.get("brainrots", []):
            if (item.get("nome", "").lower() == nome_item_sistema.lower() and
                item.get("cor", "").lower() == cor_item.lower() and
                item.get("quantidade") == quantidade_total):
                
                conta_para_entregar = conta
                break
        if conta_para_entregar:
            break
            
    if not conta_para_entregar:
        print(f"[ENTREGA] ❌ Nenhuma conta com quantidade exata ({quantidade_total}x) de '{nome_item_sistema}' ({cor_item})!")
        mensagem_sem_estoque = f"Opa, vimos sua compra de {quantidade_total}x {item_nome_ggmax} ({cor_item}) e um vendedor já foi notificado!"
        await enviar_mensagem_ggmax(codigo_pedido, mensagem_sem_estoque)
        return

    # 3. Preparar e enviar a mensagem de entrega
    id_conta = conta_para_entregar.get("id")
    channel_id_para_deletar = conta_para_entregar.get("discord_channel_id")
    
    mensagem_entrega = f"""Aqui estão os dados da sua conta:

👤 Nick: {conta_para_entregar.get('nick')}
🔒 Senha: {conta_para_entregar.get('senha')}

📧 E-mail: {conta_para_entregar.get('email')}
🌐 Site: mail.tm

Obs: O e-mail só será necessário se o Roblox pedir um código ou bloquear a conta por detectar um acesso de local diferente.
A senha do e-mail é a mesma da conta.

Qualquer dúvida, só chamar! Deixe sua avaliação ⭐"""
    
    sucesso_envio = await enviar_mensagem_ggmax(codigo_pedido, mensagem_entrega)
    
    if sucesso_envio:
        print(f"[ENTREGA] ✅ Mensagem de entrega para o pedido {codigo_pedido} enviada com sucesso!")
        
        # 4. Remover conta do estoque
        contas_atualizadas = [c for c in contas if c.get("id") != id_conta]
        data["contas"] = contas_atualizadas
        salvar_contas(data)
        print(f"[ESTOQUE] ✅ Conta ID {id_conta} ('{conta_para_entregar.get('nick')}') removida do estoque.")
        
        # 5. Marcar pedido como entregue na GGMAX
        await marcar_pedido_entregue(codigo_pedido)
        
        # 6. Agendar deleção do canal do Discord, se houver
        if channel_id_para_deletar:
            adicionar_tarefa("deletar_canal", {"channel_id": channel_id_para_deletar})
            print(f"[CANAL] 🗑️ Deleção do canal {channel_id_para_deletar} agendada.")
        
        # 7. Avaliar o cliente positivamente
        await avaliar_cliente(codigo_pedido)
        
    else:
        print(f"[ENTREGA] ❌ Falha ao enviar mensagem de entrega para o pedido {codigo_pedido}.")

def encontrar_faixa_por_renda(renda_min, renda_max):
    """Encontra o nome da faixa no config que corresponde aos valores de renda."""
    for tier in RENDA_TIERS_DATA:
        if tier.get('min') == renda_min and tier.get('max') == renda_max:
            return tier.get('nome_faixa')
    return None

async def entregar_conta_mista(codigo_pedido, quantidade_brainrots, renda_min, renda_max):
    """Processa a entrega de uma conta mista para a GGMAX usando a nova estrutura."""
    print(f"[ENTREGA MISTA] 🎁 Processando pedido {codigo_pedido} para {quantidade_brainrots}x brainrots (${renda_min}-${renda_max})...")

    # 1. Encontrar o nome da faixa correspondente
    nome_faixa = encontrar_faixa_por_renda(renda_min, renda_max)
    if not nome_faixa:
        print(f"[ENTREGA MISTA] ❌ Nenhuma faixa configurada para {renda_min}-{renda_max}!")
        # Pode-se enviar uma notificação aqui, se desejado
        return

    # 2. Buscar conta compatível no estoque
    contas_data = ler_contas_mistas()
    conta_para_entregar = None
    for conta in contas_data.get("contas_mistas", []):
        produto = conta.get("produto_misto", {})
        if produto.get("faixa") == nome_faixa and produto.get("quantidade") == quantidade_brainrots:
            conta_para_entregar = conta
            break # Encontrou a primeira conta compatível

    if not conta_para_entregar:
        print(f"[ENTREGA MISTA] ❌ Nenhuma conta em estoque para a faixa '{nome_faixa}' com {quantidade_brainrots} brainrots!")
        # ... (código de mensagem de sem estoque)
        return

    # 3. Preparar e enviar a mensagem de entrega
    id_conta = conta_para_entregar.get("id")
    channel_id_para_deletar = conta_para_entregar.get("discord_channel_id")

    mensagem_entrega = f"""Aqui estão os dados da sua conta com brainrots mistos:

👤 Nick: {conta_para_entregar.get('nick')}
🔒 Senha: {conta_para_entregar.get('senha')}

📧 E-mail: {conta_para_entregar.get('email')}
🌐 Site: mail.tm

Obs: O e-mail só será necessário se o Roblox pedir um código ou bloquear a conta por detectar um acesso de local diferente.
A senha do e-mail é a mesma da conta.

Qualquer dúvida, só chamar! Deixe sua avaliação ⭐"""

    sucesso_envio = await enviar_mensagem_ggmax(codigo_pedido, mensagem_entrega)

    if sucesso_envio:
        print(f"[ENTREGA MISTA] ✅ Conta mista ID {id_conta} entregue ({quantidade_brainrots}x brainrots {nome_faixa})!")
        
        # Marca o pedido como entregue na GGMAX
        print(f"[ENTREGA MISTA] 📋 Marcando pedido {codigo_pedido} como entregue...")
        sucesso_entrega = await marcar_pedido_entregue(codigo_pedido)
        
        if sucesso_entrega:
            print(f"[ENTREGA MISTA] ✅ Pedido marcado como entregue!")
            
            # Avalia o cliente positivamente
            print(f"[ENTREGA MISTA] ⭐ Avaliando cliente...")
            sucesso_avaliacao = await avaliar_cliente(codigo_pedido)
            
            if sucesso_avaliacao:
                print(f"[ENTREGA MISTA] ✅ Cliente avaliado positivamente!")
            else:
                print(f"[ENTREGA MISTA] ⚠️ Falha ao avaliar cliente, mas entrega foi concluída.")
        else:
            print(f"[ENTREGA MISTA] ⚠️ Falha ao marcar como entregue, mas mensagem foi enviada.")
        
        # Remove a conta do estoque e agenda deleção do canal
        if channel_id_para_deletar:
            adicionar_tarefa("deletar_canal", {"channel_id": channel_id_para_deletar})
        
        contas_data["contas_mistas"] = [c for c in contas_data["contas_mistas"] if c.get("id") != id_conta]
        salvar_contas_mistas(contas_data)
        print(f"[ENTREGA MISTA] 🗑️ Conta mista removida do estoque.")
        
        print(f"[ENTREGA MISTA] 🎉 Processo de entrega mista completo para pedido {codigo_pedido}!")
    else:
        print(f"[ENTREGA MISTA] ❌ Falha ao entregar conta mista.")

async def processar_mensagem_venda(message):
    """Processa uma mensagem que pode conter uma venda GGMAX."""
    conteudo = message.content
    
    print(f"[PROCESSAR] 🔍 Analisando mensagem para venda GGMAX...")
    print(f"[PROCESSAR] Conteúdo completo:\n{conteudo}")
    
    # Regex patterns atualizados para o formato real da GGMAX
    # Captura o código do pedido de dentro do link markdown (aceita "pedido" ou "pedidos")
    match_pedido = re.search(r"https://ggmax\.com\.br/conta/pedidos?/([a-zA-Z0-9]+)", conteudo)
    
    # Regex para produtos específicos (formato original)
    # Exemplo: "1 x [4x [🦒🍉] Girafa Celestre - $20k/s - (⚪ NORMAL)]"
    match_item_especifico_antigo = re.search(r"(\d+)\s*x\s*\[(\d+)x\s*\[.*?\]\s*(.*?)\s*-.*?-\s*\(.*?\s*(\w+)\)", conteudo)
    
    # Regex para produtos específicos (formato novo)
    # Exemplo: "1x [🎀] Las Tralaleritas - $812.5k/s - (🟡 GOLD)"
    match_item_especifico = re.search(r"(\d+)x\s*\[.*?\]\s*(.*?)\s*-\s*\$[\d.,]+[kKmM]?/s\s*-\s*\(.*?\s*(\w+)\)", conteudo)
    
    # Regex para Lucky Blocks
    # Exemplo: "5x [🟦🪽] Lucky Block - Brainrot God - (⚪ NORMAL)"
    match_lucky_block = re.search(r"(\d+)\s*x\s*\[.*?\]\s*(Lucky Block - .*?)\s*-", conteudo)
    
    # Regex para produtos mistos (formato novo)
    # Exemplo: "3x [🎁] Aleatórios - $10K/s a $50K/s CADA - (🔄 MISTOS)"
    match_item_misto = re.search(r"(\d+)x\s*\[.*?\]\s*(.*?)\s*-\s*\$(\d+)([KkMm])?/s\s*a\s*\$(\d+)([KkMm])?/s\s*CADA\s*-\s*\(.*?MISTOS\)", conteudo)
    
    # Regex para contas rebirth
    # Exemplo: "1x [🔄] Conta com Brainrots pra/para dar Rebirth do 5 ao 12"
    match_rebirth = re.search(r"(\d+)x\s*\[🔄\]\s*(.*?(?:pra|para)\s+dar\s+Rebirth.*?do\s*(\d+)\s*ao\s*(\d+))", conteudo)
    
    # Regex para Lucky Blocks (formato novo, com duas quantidades)
    # Exemplo: "1 x [5x [🟥🪽] Lucky Block - Mythic - (⚪ NORMAL)]"
    match_lucky_block_novo = re.search(r"(\d+)\s*x\s*\[(\d+)x\s*\[.*?\]\s*(Lucky Block - .*?)\s*-\s*\(.*?\)", conteudo)
    
    # Regex para Lucky Blocks (formato antigo, com uma quantidade)
    # Exemplo: "5x [🟦🪽] Lucky Block - Brainrot God - (⚪ NORMAL)"
    match_lucky_block_antigo = re.search(r"(\d+)\s*x\s*\[.*?\]\s*(Lucky Block - .*?)\s*-", conteudo)
    
    print(f"[PROCESSAR] 🔍 Resultados das regex:")
    print(f"[PROCESSAR]   Match pedido: {match_pedido is not None}")
    if match_pedido:
        print(f"[PROCESSAR]   Código pedido: {match_pedido.group(1)}")
    print(f"[PROCESSAR]   Match item específico (novo): {match_item_especifico is not None}")
    print(f"[PROCESSAR]   Match item específico (antigo): {match_item_especifico_antigo is not None}")
    print(f"[PROCESSAR]   Match lucky block: {match_lucky_block is not None}")
    print(f"[PROCESSAR]   Match item misto: {match_item_misto is not None}")
    print(f"[PROCESSAR]   Match rebirth: {match_rebirth is not None}")
    print(f"[PROCESSAR]   Match lucky block (novo): {match_lucky_block_novo is not None}")
    print(f"[PROCESSAR]   Match lucky block (antigo): {match_lucky_block_antigo is not None}")
    
    if match_pedido:
        codigo_pedido = match_pedido.group(1)
        
        # Verifica PRIMEIRO se é uma conta rebirth (tem maior prioridade)
        if match_rebirth:
            print(f"[PROCESSAR]   Grupos rebirth: {match_rebirth.groups()}")
            quantidade_contas = int(match_rebirth.group(1))
            descricao_rebirth = match_rebirth.group(2).strip()
            nivel_min = int(match_rebirth.group(3))
            nivel_max = int(match_rebirth.group(4))
            
            print(f"[VENDA] 🔄 Venda REBIRTH detectada: {codigo_pedido}")
            print(f"[DETALHES] Descrição: {descricao_rebirth} | Quantidade: {quantidade_contas} | Níveis: {nivel_min}-{nivel_max}")
            
            await entregar_conta_rebirth(codigo_pedido, quantidade_contas, descricao_rebirth, nivel_min, nivel_max)
            
        # Verifica se é um produto misto
        elif match_item_misto:
            print(f"[PROCESSAR]   Grupos item misto: {match_item_misto.groups()}")
            quantidade_brainrots = int(match_item_misto.group(1))
            nome_produto = match_item_misto.group(2).strip()
            
            # Processa valor mínimo com unidade
            valor_min = int(match_item_misto.group(3))
            unidade_min = match_item_misto.group(4) or 'K'  # Default para K se não especificado
            if unidade_min.upper() == 'M':
                renda_min = valor_min * 1000000  # Milhões
            else:
                renda_min = valor_min * 1000     # Milhares
            
            # Processa valor máximo com unidade
            valor_max = int(match_item_misto.group(5))
            unidade_max = match_item_misto.group(6) or 'K'  # Default para K se não especificado
            if unidade_max.upper() == 'M':
                renda_max = valor_max * 1000000  # Milhões
            else:
                renda_max = valor_max * 1000     # Milhares
            
            print(f"[VENDA] 🎁 Venda MISTA detectada: {codigo_pedido}")
            print(f"[DETALHES] Produto: {nome_produto} | Quantidade: {quantidade_brainrots} | Faixa: ${renda_min:,} - ${renda_max:,}")
            
            await entregar_conta_mista(codigo_pedido, quantidade_brainrots, renda_min, renda_max)
            
        # Verifica se é um Lucky Block (tem prioridade sobre específico)
        elif match_lucky_block_novo:
            print(f"[PROCESSAR]   Grupos lucky block (novo): {match_lucky_block_novo.groups()}")
            quantidade_pedido = int(match_lucky_block_novo.group(1))
            quantidade_item = int(match_lucky_block_novo.group(2))
            quantidade_total = quantidade_pedido * quantidade_item
            nome_item = match_lucky_block_novo.group(3).strip()

            print(f"[VENDA] 📦 Venda de LUCKY BLOCK detectada: {codigo_pedido}")
            print(f"[DETALHES] Item: {nome_item} | Quantidade: {quantidade_total}")

            await entregar_lucky_block(codigo_pedido, nome_item, quantidade_total)
            
        elif match_lucky_block_antigo:
            print(f"[PROCESSAR]   Grupos lucky block (antigo): {match_lucky_block_antigo.groups()}")
            quantidade_total = int(match_lucky_block_antigo.group(1))
            nome_item = match_lucky_block_antigo.group(2).strip()

            print(f"[VENDA] 📦 Venda de LUCKY BLOCK detectada: {codigo_pedido}")
            print(f"[DETALHES] Item: {nome_item} | Quantidade: {quantidade_total}")

            await entregar_lucky_block(codigo_pedido, nome_item, quantidade_total)

        # Verifica se é um produto específico (apenas se NÃO for misto ou lucky block)
        elif match_item_especifico or match_item_especifico_antigo:
            # Usa o formato novo se disponível, senão usa o antigo
            match_atual = match_item_especifico if match_item_especifico else match_item_especifico_antigo
            
            print(f"[PROCESSAR]   Grupos item específico: {match_atual.groups()}")
            
            if match_item_especifico:
                # Formato novo: "1x [🎀] Las Tralaleritas - $812.5k/s - (🟡 GOLD)"
                quantidade_total = int(match_atual.group(1))
                nome_item = match_atual.group(2).strip()
                cor_item = match_atual.group(3).strip()
            else:
                # Formato antigo: "1 x [4x [🦒🍉] Girafa Celestre - $20k/s - (⚪ NORMAL)]"
                quantidade_pedido = int(match_atual.group(1))
                quantidade_item = int(match_atual.group(2))
                nome_item = match_atual.group(3).strip()
                cor_item = match_atual.group(4).strip()
                quantidade_total = quantidade_pedido * quantidade_item
            
            print(f"[VENDA] 🛒 Venda ESPECÍFICA detectada: {codigo_pedido}")
            print(f"[DETALHES] Item: {nome_item} | Cor: {cor_item} | Quantidade: {quantidade_total}")
            
            await entregar_conta_especifica(codigo_pedido, nome_item, cor_item, quantidade_total)
            
        else:
            print(f"[MONITOR] 📝 Mensagem com pedido mas sem formato reconhecido: {conteudo[:50]}...")
    else:
        print(f"[MONITOR] 📝 Mensagem não é uma venda GGMAX: {conteudo[:50]}...")
        # Debug: mostrar o que foi capturado
        if match_rebirth:
            print(f"[DEBUG] Item rebirth capturado: {match_rebirth.groups()}")
        elif match_item_especifico:
            print(f"[DEBUG] Item específico (novo) capturado: {match_item_especifico.groups()}")
        elif match_item_especifico_antigo:
            print(f"[DEBUG] Item específico (antigo) capturado: {match_item_especifico_antigo.groups()}")
        elif match_lucky_block_novo:
            print(f"[DEBUG] Item lucky block (novo) capturado: {match_lucky_block_novo.groups()}")
        elif match_lucky_block_antigo:
            print(f"[DEBUG] Item lucky block (antigo) capturado: {match_lucky_block_antigo.groups()}")
        elif match_item_misto:
            print(f"[DEBUG] Item misto capturado: {match_item_misto.groups()}")
        else:
            print(f"[DEBUG] ❌ Nenhum item capturado")

async def entregar_lucky_block(codigo_pedido, item_nome_ggmax, quantidade_total):
    """
    Processa a entrega de uma conta com um Lucky Block específico.
    """
    print(f"[ENTREGA LUCKY BLOCK] 🔍 Processando pedido {codigo_pedido} para '{item_nome_ggmax}' x{quantidade_total}...")
    
    data = ler_contas()
    contas = data.get("contas", [])
    
    # 1. Encontrar o nome do Lucky Block no nosso sistema por similaridade
    nomes_disponiveis = {lb['nome'] for lb in LUCKY_BLOCKS_DATA}
    matches = difflib.get_close_matches(item_nome_ggmax, nomes_disponiveis, n=1, cutoff=0.8)
    
    nome_item_sistema = None
    if matches:
        nome_item_sistema = matches[0]
        if nome_item_sistema.lower() != item_nome_ggmax.lower():
            print(f"[ENTREGA LUCKY BLOCK] ⚠️ Nome correspondido por similaridade: '{item_nome_ggmax}' -> '{nome_item_sistema}'")
    else:
        print(f"[ENTREGA LUCKY BLOCK] ❌ Não foi encontrado um Lucky Block similar a '{item_nome_ggmax}' no sistema.")
        return

    # 2. Buscar conta que corresponde ao Lucky Block e quantidade
    conta_para_entregar = None
    for conta in contas:
        # Pula contas que não têm itens
        if not conta.get("brainrots"):
            continue
            
        # Considera apenas contas com um único item (contas puras de Lucky Block)
        if len(conta["brainrots"]) == 1:
            item = conta["brainrots"][0]
            if (item.get("is_lucky_block", False) and
                item.get("nome", "").lower() == nome_item_sistema.lower() and
                item.get("quantidade") == quantidade_total):
                
                conta_para_entregar = conta
                break
            
    if not conta_para_entregar:
        print(f"[ENTREGA LUCKY BLOCK] ❌ Nenhuma conta com a quantidade exata ({quantidade_total}x) de '{nome_item_sistema}'!")
        mensagem_sem_estoque = f"Opa, vimos sua compra de {quantidade_total}x {item_nome_ggmax} e um vendedor já foi notificado!"
        await enviar_mensagem_ggmax(codigo_pedido, mensagem_sem_estoque)
        return

    # 3. Preparar e enviar a mensagem de entrega
    id_conta = conta_para_entregar.get("id")
    channel_id_para_deletar = conta_para_entregar.get("discord_channel_id")
    
    mensagem_entrega = f"""Aqui estão os dados da sua conta:

👤 Nick: {conta_para_entregar.get('nick')}
🔒 Senha: {conta_para_entregar.get('senha')}

📧 E-mail: {conta_para_entregar.get('email')}
🌐 Site: mail.tm

Obs: O e-mail só será necessário se o Roblox pedir um código ou bloquear a conta por detectar um acesso de local diferente.
A senha do e-mail é a mesma da conta.

Qualquer dúvida, só chamar! Deixe sua avaliação ⭐"""
    
    sucesso_envio = await enviar_mensagem_ggmax(codigo_pedido, mensagem_entrega)
    
    if sucesso_envio:
        print(f"[ENTREGA LUCKY BLOCK] ✅ Mensagem de entrega para o pedido {codigo_pedido} enviada com sucesso!")
        
        # 4. Remover conta do estoque
        contas_atualizadas = [c for c in contas if c.get("id") != id_conta]
        data["contas"] = contas_atualizadas
        salvar_contas(data)
        print(f"[ESTOQUE] ✅ Conta ID {id_conta} ('{conta_para_entregar.get('nick')}') removida do estoque.")
        
        # 5. Marcar pedido como entregue na GGMAX
        await marcar_pedido_entregue(codigo_pedido)
        
        # 6. Agendar deleção do canal do Discord, se houver
        if channel_id_para_deletar:
            adicionar_tarefa("deletar_canal", {"channel_id": channel_id_para_deletar})
            print(f"[CANAL] 🗑️ Deleção do canal {channel_id_para_deletar} agendada.")
        
        # 7. Avaliar o cliente positivamente
        await avaliar_cliente(codigo_pedido)
        
    else:
        print(f"[ENTREGA LUCKY BLOCK] ❌ Falha ao enviar mensagem de entrega para o pedido {codigo_pedido}.")

async def entregar_conta_rebirth(codigo_pedido, quantidade_contas, descricao_rebirth, nivel_min, nivel_max):
    """
    Processa a entrega de uma conta rebirth para a GGMAX.
    """
    print(f"[ENTREGA REBIRTH] 🔄 Processando pedido {codigo_pedido} para {quantidade_contas}x conta(s) rebirth...")
    
    # Verifica se temos contas rebirth disponíveis
    data_rebirth = ler_contas_rebirth()
    contas_rebirth = data_rebirth.get("contas_rebirth", [])
    
    if len(contas_rebirth) < quantidade_contas:
        print(f"[ENTREGA REBIRTH] ❌ Estoque insuficiente! Solicitado: {quantidade_contas}, Disponível: {len(contas_rebirth)}")
        mensagem_sem_estoque = f"Opa, vimos sua compra de {quantidade_contas}x conta(s) para rebirth e um vendedor já foi notificado!"
        await enviar_mensagem_ggmax(codigo_pedido, mensagem_sem_estoque)
        return
    
    # Pega as primeiras contas disponíveis
    contas_para_entregar = contas_rebirth[:quantidade_contas]
    
    # Prepara a mensagem de entrega
    if quantidade_contas == 1:
        # Entrega de uma conta
        conta = contas_para_entregar[0]
        mensagem_entrega = f"""Aqui estão os dados da sua conta para rebirth:

👤 Nick: {conta.get('nick')}
🔒 Senha: {conta.get('senha')}

📧 E-mail: {conta.get('email')}
🌐 Site: mail.tm

🔄 Esta conta contém brainrots adequados para dar rebirth do nível {nivel_min} ao {nivel_max}.

Obs: O e-mail só será necessário se o Roblox pedir um código ou bloquear a conta por detectar um acesso de local diferente.
A senha do e-mail é a mesma da conta.

Qualquer dúvida, só chamar! Deixe sua avaliação ⭐"""
    else:
        # Entrega múltipla
        mensagem_entrega = f"Aqui estão os dados das suas {quantidade_contas} contas para rebirth:\n\n"
        
        for i, conta in enumerate(contas_para_entregar, 1):
            mensagem_entrega += f"""**CONTA {i}:**
👤 Nick: {conta.get('nick')}
🔒 Senha: {conta.get('senha')}
📧 E-mail: {conta.get('email')}

"""
        
        mensagem_entrega += f"""🌐 Site dos e-mails: mail.tm

🔄 Estas contas contêm brainrots adequados para dar rebirth do nível {nivel_min} ao {nivel_max}.

Obs: O e-mail só será necessário se o Roblox pedir um código ou bloquear a conta por detectar um acesso de local diferente.
A senha do e-mail é a mesma da conta.

Qualquer dúvida, só chamar! Deixe sua avaliação ⭐"""
    
    # Envia a mensagem
    sucesso_envio = await enviar_mensagem_ggmax(codigo_pedido, mensagem_entrega)
    
    if sucesso_envio:
        print(f"[ENTREGA REBIRTH] ✅ Mensagem de entrega para o pedido {codigo_pedido} enviada com sucesso!")
        
        # Remove as contas entregues do estoque
        contas_restantes = contas_rebirth[quantidade_contas:]
        data_rebirth["contas_rebirth"] = contas_restantes
        salvar_contas_rebirth(data_rebirth)
        
        # Log das contas removidas e agenda deleção dos canais Discord
        for conta in contas_para_entregar:
            print(f"[ESTOQUE REBIRTH] ✅ Conta '{conta.get('nick')}' removida do estoque rebirth.")
            
            # Agenda deleção do canal Discord, se houver
            channel_id = conta.get("discord_channel_id")
            if channel_id:
                adicionar_tarefa("deletar_canal", {"channel_id": channel_id})
                print(f"[CANAL] 🗑️ Deleção do canal {channel_id} agendada para conta rebirth '{conta.get('nick')}'.")
        
        # Marcar pedido como entregue na GGMAX
        await marcar_pedido_entregue(codigo_pedido)
        
        # Avaliar o cliente positivamente
        await avaliar_cliente(codigo_pedido)
        
    else:
        print(f"[ENTREGA REBIRTH] ❌ Falha ao enviar mensagem de entrega para o pedido {codigo_pedido}.")

# --- Estrutura do Bot ---
class AccountManagerClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.persistent_views_loaded = False

    async def setup_hook(self):
        # Recarrega a view persistente apenas uma vez.
        if not self.persistent_views_loaded:
            self.add_view(ManageAccountView()) # Registra a view stateless
            print(f"[VIEWS] View de gerenciamento de contas registrada.")
            self.persistent_views_loaded = True
        
        await self.tree.sync()
        # Inicia o loop de tarefas em segundo plano
        self.task_processor.start()

    # Define o loop que rodará em segundo plano
    @tasks.loop(seconds=15)
    async def task_processor(self):
        await processar_tarefas_pendentes(self)

    @task_processor.before_loop
    async def before_task_processor(self):
        await self.wait_until_ready() # Garante que o bot esteja conectado antes de começar


intents = discord.Intents.default()
intents.message_content = True  # Necessário para ler conteúdo das mensagens
intents.messages = True  # Necessário para receber eventos de mensagem
client = AccountManagerClient(intents=intents)

@client.event
async def on_ready():
    if client.user:
        print(f'Logado como {client.user} (ID: {client.user.id})')
    else:
        print('Logado, mas o objeto client.user é None.')
    print('------')
    # NOTA: O arquivo json_manager.py e o contas.json precisam ser atualizados manualmente
    # para usar uma lista única "contas" em vez de "contas_de_estoque" e "contas_para_venda".
    carregar_configs_globais()
    inicializar_json()
    
    # Inicializa o token da GGMAX
    await renovar_access_token()
    
    if CANAL_VENDAS_ID:
        print(f"[MONITOR] 👁️ Monitorando canal de vendas: {CANAL_VENDAS_ID}")
        
        # Verifica se o bot tem acesso ao canal
        canal = client.get_channel(CANAL_VENDAS_ID)
        if canal:
            print(f"[MONITOR] ✅ Canal encontrado: {canal.name}")
            # Verifica permissões
            if hasattr(canal, 'permissions_for'):
                perms = canal.permissions_for(canal.guild.me)
                print(f"[MONITOR] 📋 Permissões no canal:")
                print(f"[MONITOR]   - Ler mensagens: {perms.read_messages}")
                print(f"[MONITOR]   - Ver histórico: {perms.read_message_history}")
                print(f"[MONITOR]   - Enviar mensagens: {perms.send_messages}")
        else:
            print(f"[MONITOR] ❌ Canal {CANAL_VENDAS_ID} não encontrado ou sem acesso!")
    else:
        print("[MONITOR] ⚠️ Canal de vendas não configurado no config.json")

@client.event
async def on_message(message):
    """Monitora mensagens no canal de vendas para detectar vendas GGMAX."""
    # Debug: Log todas as mensagens recebidas
    print(f"[DEBUG] 📨 Mensagem recebida:")
    print(f"[DEBUG]   Canal ID: {message.channel.id}")
    print(f"[DEBUG]   Autor: {message.author.name}")
    print(f"[DEBUG]   É bot próprio: {message.author == client.user}")
    print(f"[DEBUG]   CANAL_VENDAS_ID configurado: {CANAL_VENDAS_ID}")
    print(f"[DEBUG]   Conteúdo (primeiros 100 chars): {message.content[:100]}...")
    
    # Ignora mensagens do próprio bot
    if message.author == client.user:
        print(f"[DEBUG] ⏭️ Ignorando mensagem do próprio bot")
        return
    
    # Verifica se a mensagem é do canal de vendas configurado
    if CANAL_VENDAS_ID and message.channel.id == CANAL_VENDAS_ID:
        print(f"[MONITOR] 📨 Nova mensagem no canal de vendas de {message.author.name}:")
        print(f"[CONTEÚDO] {message.content}")
        await processar_mensagem_venda(message)
    else:
        print(f"[DEBUG] ⏭️ Mensagem não é do canal de vendas configurado")
        print(f"[DEBUG]   Canal atual: {message.channel.id}")
        print(f"[DEBUG]   Canal esperado: {CANAL_VENDAS_ID}")
        print(f"[DEBUG]   Match: {message.channel.id == CANAL_VENDAS_ID}")
    
# --- Definição dos Novos Grupos de Comandos ---
add_group = app_commands.Group(name="add", description="Adiciona contas ou itens.")
remove_group = app_commands.Group(name="remove", description="Remove contas ou itens.")
search_group = app_commands.Group(name="search", description="Busca itens nas contas.")
config_group = app_commands.Group(name="config", description="Gerencia configurações do sistema.")

# --- Funções de Configuração ---

def salvar_config_global():
    """Salva as configurações globais no arquivo config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(CONFIG_DATA, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {CONFIG_FILE}: {e}")
        return False

def salvar_brainrots_config():
    """Salva as configurações de brainrots no arquivo brainrots_config.json."""
    try:
        with open(BRAINROTS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"brainrots": BRAINROTS_DATA}, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {BRAINROTS_CONFIG_FILE}: {e}")
        return False

def salvar_cores_config():
    """Salva as configurações de cores no arquivo cores_config.json."""
    try:
        with open(CORES_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"cores": CORES_DATA}, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {CORES_CONFIG_FILE}: {e}")
        return False

def salvar_mutations_config():
    """Salva as configurações de mutações no arquivo mutations_config.json."""
    try:
        with open(MUTATIONS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"mutacoes": MUTATIONS_DATA}, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar {MUTATIONS_CONFIG_FILE}: {e}")
        return False

# --- Comandos do Grupo /config ---

@config_group.command(name="ggmax_token", description="Atualiza o token de refresh da GGMAX.")
@app_commands.describe(
    novo_token="O novo GGMAX_REFRESH_TOKEN a ser configurado."
)
async def config_ggmax_token(interaction: discord.Interaction, novo_token: str):
    await interaction.response.defer(ephemeral=True)
    
    # Valida se o token parece ser válido (formato JWT básico)
    if not novo_token or len(novo_token.split('.')) != 3:
        await interaction.followup.send("❌ Token inválido. Certifique-se de que é um token JWT válido (deve ter 3 partes separadas por pontos).", ephemeral=True)
        return
    
    # Salva o token antigo para rollback em caso de erro
    token_antigo = CONFIG_DATA.get("GGMAX_REFRESH_TOKEN")
    
    try:
        # Atualiza o token na memória
        CONFIG_DATA["GGMAX_REFRESH_TOKEN"] = novo_token
        
        # Salva no arquivo
        if not salvar_config_global():
            # Rollback em caso de erro
            if token_antigo:
                CONFIG_DATA["GGMAX_REFRESH_TOKEN"] = token_antigo
            await interaction.followup.send("❌ Erro ao salvar a configuração no arquivo.", ephemeral=True)
            return
        
        # Testa o novo token tentando renovar o access token
        print(f"[CONFIG] 🔄 Testando novo GGMAX_REFRESH_TOKEN...")
        sucesso_teste = await renovar_access_token()
        
        if sucesso_teste:
            await interaction.followup.send(
                "✅ **GGMAX_REFRESH_TOKEN atualizado com sucesso!**\n"
                f"🔄 Novo token configurado e testado\n"
                f"✅ Access token renovado automaticamente\n"
                f"📁 Configuração salva em `config.json`", 
                ephemeral=True
            )
            print(f"[CONFIG] ✅ GGMAX_REFRESH_TOKEN atualizado via comando Discord")
        else:
            # Rollback se o teste falhar
            if token_antigo:
                CONFIG_DATA["GGMAX_REFRESH_TOKEN"] = token_antigo
                salvar_config_global()
            
            await interaction.followup.send(
                "❌ **Erro: Token inválido ou expirado!**\n"
                f"🔄 Configuração restaurada para o token anterior\n"
                f"ℹ️ Verifique se o token está correto e não expirou", 
                ephemeral=True
            )
            print(f"[CONFIG] ❌ Teste do novo GGMAX_REFRESH_TOKEN falhou - rollback executado")
            
    except Exception as e:
        # Rollback em caso de exceção
        if token_antigo:
            CONFIG_DATA["GGMAX_REFRESH_TOKEN"] = token_antigo
            salvar_config_global()
        
        await interaction.followup.send(f"❌ Erro inesperado ao atualizar token: {str(e)}", ephemeral=True)
        print(f"[CONFIG] ❌ Erro ao atualizar GGMAX_REFRESH_TOKEN: {e}")



@config_group.command(name="adicionar_cor", description="Adiciona uma nova cor ao sistema.")
@app_commands.describe(
    nome="Nome da nova cor",
    multiplicador="Multiplicador da cor (ex: 1.5)",
    emoji="Emoji representativo da cor"
)
async def config_adicionar_cor(interaction: discord.Interaction, nome: str, multiplicador: float, emoji: str):
    await interaction.response.defer(ephemeral=True)
    
    # Verifica se a cor já existe
    for cor in CORES_DATA:
        if cor["nome"].lower() == nome.lower():
            await interaction.followup.send(f"❌ A cor `{nome}` já existe!", ephemeral=True)
            return
    
    if multiplicador <= 0:
        await interaction.followup.send("❌ O multiplicador deve ser maior que 0!", ephemeral=True)
        return
    
    # Adiciona a nova cor
    nova_cor = {
        "nome": nome,
        "multiplicador": multiplicador,
        "emoji": emoji
    }
    
    CORES_DATA.append(nova_cor)
    
    if salvar_cores_config():
        embed = discord.Embed(
            title="✅ Cor Adicionada com Sucesso!",
            color=discord.Color.green()
        )
        embed.add_field(name="Nome", value=nome, inline=True)
        embed.add_field(name="Multiplicador", value=f"{multiplicador}x", inline=True)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.set_footer(text="A nova cor já está disponível nos menus!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"[CONFIG] ✅ Nova cor adicionada via Discord: {nome} ({multiplicador}x) {emoji}")
    else:
        # Remove da memória se falhou ao salvar
        CORES_DATA.remove(nova_cor)
        await interaction.followup.send("❌ Erro ao salvar a configuração. Tente novamente.", ephemeral=True)

@config_group.command(name="adicionar_brainrot", description="Adiciona um novo brainrot ao sistema.")
@app_commands.describe(
    nome="Nome do novo brainrot",
    renda_base="Renda base do brainrot (número inteiro)",
    emoji="Emoji representativo do brainrot"
)
async def config_adicionar_brainrot(interaction: discord.Interaction, nome: str, renda_base: int, emoji: str):
    await interaction.response.defer(ephemeral=True)
    
    # Verifica se o brainrot já existe
    for brainrot in BRAINROTS_DATA:
        if brainrot["nome"].lower() == nome.lower():
            await interaction.followup.send(f"❌ O brainrot `{nome}` já existe!", ephemeral=True)
            return
    
    if renda_base <= 0:
        await interaction.followup.send("❌ A renda base deve ser maior que 0!", ephemeral=True)
        return
    
    # Adiciona o novo brainrot
    novo_brainrot = {
        "nome": nome,
        "renda_base": renda_base,
        "emoji": emoji
    }
    
    BRAINROTS_DATA.append(novo_brainrot)
    
    if salvar_brainrots_config():
        embed = discord.Embed(
            title="✅ Brainrot Adicionado com Sucesso!",
            color=discord.Color.green()
        )
        embed.add_field(name="Nome", value=nome, inline=True)
        embed.add_field(name="Renda Base", value=f"{renda_base:,} coins/s".replace(",", "."), inline=True)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.set_footer(text="O novo brainrot já está disponível nos menus!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"[CONFIG] ✅ Novo brainrot adicionado via Discord: {nome} ({renda_base}) {emoji}")
    else:
        # Remove da memória se falhou ao salvar
        BRAINROTS_DATA.remove(novo_brainrot)
        await interaction.followup.send("❌ Erro ao salvar a configuração. Tente novamente.", ephemeral=True)

@config_group.command(name="adicionar_mutacao", description="Adiciona uma nova mutação ao sistema.")
@app_commands.describe(
    nome="Nome da nova mutação",
    multiplicador="Multiplicador da mutação (ex: 4.5)",
    descricao="Descrição da mutação",
    emoji="Emoji representativo da mutação"
)
async def config_adicionar_mutacao(interaction: discord.Interaction, nome: str, multiplicador: float, descricao: str, emoji: str):
    await interaction.response.defer(ephemeral=True)
    
    # Verifica se a mutação já existe
    for mutacao in MUTATIONS_DATA:
        if mutacao["nome"].lower() == nome.lower():
            await interaction.followup.send(f"❌ A mutação `{nome}` já existe!", ephemeral=True)
            return
    
    if multiplicador <= 0:
        await interaction.followup.send("❌ O multiplicador deve ser maior que 0!", ephemeral=True)
        return
    
    # Adiciona a nova mutação
    nova_mutacao = {
        "nome": nome,
        "multiplicador": multiplicador,
        "descricao": descricao,
        "emoji": emoji
    }
    
    MUTATIONS_DATA.append(nova_mutacao)
    
    if salvar_mutations_config():
        embed = discord.Embed(
            title="✅ Mutação Adicionada com Sucesso!",
            color=discord.Color.green()
        )
        embed.add_field(name="Nome", value=nome, inline=True)
        embed.add_field(name="Multiplicador", value=f"{multiplicador}x", inline=True)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.add_field(name="Descrição", value=descricao, inline=False)
        embed.set_footer(text="A nova mutação já está disponível nos menus!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"[CONFIG] ✅ Nova mutação adicionada via Discord: {nome} ({multiplicador}x) {emoji}")
    else:
        # Remove da memória se falhou ao salvar
        MUTATIONS_DATA.remove(nova_mutacao)
        await interaction.followup.send("❌ Erro ao salvar a configuração. Tente novamente.", ephemeral=True)

@config_group.command(name="recarregar", description="Recarrega todas as configurações dos arquivos JSON.")
async def config_recarregar(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Recarrega todas as configurações
        carregar_configs_globais()
        
        embed = discord.Embed(
            title="✅ Configurações Recarregadas!",
            description="Todas as configurações foram recarregadas dos arquivos JSON.",
            color=discord.Color.green()
        )
        
        # Mostra um resumo das configurações carregadas
        embed.add_field(name="🎨 Cores", value=f"{len(CORES_DATA)} itens", inline=True)
        embed.add_field(name="🧠 Brainrots", value=f"{len(BRAINROTS_DATA)} itens", inline=True) 
        embed.add_field(name="📦 Lucky Blocks", value=f"{len(LUCKY_BLOCKS_DATA)} itens", inline=True)
        embed.add_field(name="🧬 Mutações", value=f"{len(MUTATIONS_DATA)} itens", inline=True)
        embed.add_field(name="📊 Faixas de Renda", value=f"{len(RENDA_TIERS_DATA)} faixas", inline=True)
        
        embed.set_footer(text="As alterações já estão ativas no sistema!")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"[CONFIG] ✅ Configurações recarregadas via comando Discord")
        
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao recarregar configurações: {str(e)}", ephemeral=True)
        print(f"[CONFIG] ❌ Erro ao recarregar configurações: {e}")

# --- Comandos do Grupo /add ---

@add_group.command(name="conta", description="Adiciona uma nova conta específica e abre o menu de itens.")
@app_commands.describe(
    nick="O nick da conta.", 
    senha="A senha da conta (máximo 10 caracteres)", 
    email="O email associado à conta."
)
async def add_conta(interaction: discord.Interaction, nick: str, senha: str, email: str):
    await interaction.response.defer(ephemeral=True)
    
    if len(senha) > 10:
        await interaction.followup.send("❌ A senha deve ter no máximo 10 caracteres.", ephemeral=True)
        return
    
    data = ler_contas()
    
    contas = data.get("contas", [])
    if any(c["nick"].lower() == nick.lower() for c in contas):
        await interaction.followup.send(f"❌ Conta `{nick}` já existe.")
        return
        
    novo_id = max([c.get("id", 0) for c in contas] + [0]) + 1
    
    nova_conta = {
        "id": novo_id, 
        "nick": nick, 
        "senha": senha, 
        "email": email,
        "brainrots": []
    }
    
    contas.append(nova_conta)
    data["contas"] = contas
    
    salvar_contas(data)

    # Prepara a view para adicionar itens imediatamente
    view = ItemTypeSelectView(nick_estoque=nick)
    
    await interaction.followup.send(
        f"✅ Conta `{nick}` adicionada. Selecione o tipo de item:", 
        view=view, 
        ephemeral=True
    )

@add_group.command(name="conta_mista", description="Adiciona uma nova conta para produtos mistos.")
@app_commands.describe(
    nick="O nick da conta.",
    senha="A senha da conta.",
    email="O email da conta.",
    faixa="A faixa de renda dos brainrots nesta conta.",
    quantidade="O número de brainrots que esta conta contém."
)
@app_commands.autocomplete(faixa=faixa_renda_autocomplete)
async def add_conta_mista(interaction: discord.Interaction, nick: str, senha: str, email: str, faixa: str, quantidade: int):
    await interaction.response.defer(ephemeral=True)

    data = ler_contas_mistas()
    contas = data.get("contas_mistas", [])

    if any(c["nick"].lower() == nick.lower() for c in contas):
        await interaction.followup.send(f"❌ Conta `{nick}` já existe.")
        return

    # Valida se a faixa de renda escolhida é válida
    faixas_validas = [tier['nome_faixa'] for tier in RENDA_TIERS_DATA]
    if faixa not in faixas_validas:
        await interaction.followup.send(f"❌ Faixa de renda `{faixa}` inválida.")
        return

    if quantidade <= 0:
        await interaction.followup.send("❌ A quantidade deve ser um número positivo.")
        return

    novo_id = max([c.get("id", 0) for c in contas] + [0]) + 1
    
    nova_conta = {
        "id": novo_id,
        "nick": nick,
        "senha": senha,
        "email": email,
        "produto_misto": {
            "faixa": faixa,
            "quantidade": quantidade
        }
    }

    contas.append(nova_conta)
    data["contas_mistas"] = contas
    salvar_contas_mistas(data)

    # Cria o canal Discord para a conta mista
    if interaction.guild:
        await atualizar_canal_conta_mista(interaction.guild, nova_conta)
        # Salva novamente para incluir os IDs do canal e mensagem
        data["contas_mistas"] = contas
        salvar_contas_mistas(data)

    await interaction.followup.send(
        f"✅ Conta mista `{nick}` adicionada com sucesso!\n"
        f"**Faixa:** {faixa}\n"
        f"**Quantidade:** {quantidade} brainrots\n"
        f"**Canal:** Criado automaticamente no Discord"
    )

# --- Comandos do Grupo /remove ---

@remove_group.command(name="conta", description="Remove uma conta inteira (ação imediata).")
@app_commands.autocomplete(nick_estoque=nick_autocomplete)
@app_commands.describe(nick_estoque="O nick da conta a ser removida.")
async def remove_conta(interaction: discord.Interaction, nick_estoque: str):
    await interaction.response.defer(ephemeral=True)
    
    # Busca em contas normais
    data = ler_contas()
    contas = data.get("contas", [])
    conta_a_remover = next((c for c in contas if c["nick"].lower() == nick_estoque.lower()), None)
    
    if conta_a_remover:
        # Remove da lista de contas normais
        initial_count = len(contas)
        data["contas"] = [c for c in contas if c["id"] != conta_a_remover["id"]]
        
        if len(data["contas"]) < initial_count:
            salvar_contas(data)
            
            # Deleta o canal associado, se houver
            channel_id = conta_a_remover.get("discord_channel_id")
            if channel_id and interaction.guild:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Conta removida pelo bot.")
                        print(f"[CANAL] Canal '{channel.name}' deletado com sucesso.")
                    except discord.Forbidden:
                        print(f"[ERRO DE PERMISSÃO] Bot sem permissão para deletar o canal '{channel.name}'.")
                    except Exception as e:
                        print(f"[ERRO INESPERADO] Falha ao deletar o canal '{channel.name}': {e}")

            await interaction.followup.send(f"✅ A conta específica `{nick_estoque}` e seu canal foram removidos permanentemente.", ephemeral=True)
            return
    
    # Se não encontrou em contas normais, busca em contas rebirth
    data_rebirth = ler_contas_rebirth()
    contas_rebirth = data_rebirth.get("contas_rebirth", [])
    conta_rebirth_a_remover = next((c for c in contas_rebirth if c["nick"].lower() == nick_estoque.lower()), None)
    
    if conta_rebirth_a_remover:
        # Remove da lista de contas rebirth
        initial_count = len(contas_rebirth)
        data_rebirth["contas_rebirth"] = [c for c in contas_rebirth if c["id"] != conta_rebirth_a_remover["id"]]
        
        if len(data_rebirth["contas_rebirth"]) < initial_count:
            salvar_contas_rebirth(data_rebirth)
            
            # Deleta o canal associado, se houver
            channel_id = conta_rebirth_a_remover.get("discord_channel_id")
            if channel_id and interaction.guild:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Conta rebirth removida pelo bot.")
                        print(f"[CANAL] Canal '{channel.name}' deletado com sucesso.")
                    except discord.Forbidden:
                        print(f"[ERRO DE PERMISSÃO] Bot sem permissão para deletar o canal '{channel.name}'.")
                    except Exception as e:
                        print(f"[ERRO INESPERADO] Falha ao deletar o canal '{channel.name}': {e}")

            await interaction.followup.send(f"✅ A conta rebirth `{nick_estoque}` e seu canal foram removidos permanentemente.", ephemeral=True)
            return
    
    # Se não encontrou em nenhum lugar
    await interaction.followup.send(f"❌ Conta `{nick_estoque}` não encontrada (verificado em contas normais e rebirth).", ephemeral=True)

@remove_group.command(name="conta_mista", description="Remove uma conta mista inteira (ação imediata).")
@app_commands.autocomplete(nick_estoque=nick_mista_autocomplete)
@app_commands.describe(nick_estoque="O nick da conta mista a ser removida.")
async def remove_conta_mista(interaction: discord.Interaction, nick_estoque: str):
    await interaction.response.defer(ephemeral=True)
    data = ler_contas_mistas()
    
    contas = data.get("contas_mistas", [])
    conta_a_remover = next((c for c in contas if c["nick"].lower() == nick_estoque.lower()), None)
    
    if not conta_a_remover:
        await interaction.followup.send(f"❌ Conta mista `{nick_estoque}` não encontrada.", ephemeral=True)
        return

    initial_count = len(contas)
    data["contas_mistas"] = [c for c in contas if c["id"] != conta_a_remover["id"]]
    
    if len(data["contas_mistas"]) < initial_count:
        salvar_contas_mistas(data)
        
        # Deleta o canal associado, se houver
        channel_id = conta_a_remover.get("discord_channel_id")
        if channel_id and interaction.guild:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete(reason="Conta mista removida pelo bot.")
                    print(f"[CANAL] Canal '{channel.name}' deletado com sucesso.")
                except discord.Forbidden:
                    print(f"[ERRO DE PERMISSÃO] Bot sem permissão para deletar o canal '{channel.name}'.")
                except Exception as e:
                    print(f"[ERRO INESPERADO] Falha ao deletar o canal '{channel.name}': {e}")

        await interaction.followup.send(f"✅ A conta mista `{nick_estoque}` e seu canal foram removidos permanentemente.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Falha ao remover a conta mista `{nick_estoque}`. Pode já ter sido removida.", ephemeral=True)

@remove_group.command(name="item", description="Remove um item de uma conta.")
@app_commands.autocomplete(nick_estoque=nick_autocomplete)
@app_commands.describe(nick_estoque="O nick da conta da qual o item será removido.")
async def remove_item(interaction: discord.Interaction, nick_estoque: str):
    await interaction.response.defer(ephemeral=True)
    data = ler_contas()
    conta_encontrada = next((c for c in data.get("contas", []) if c["nick"].lower() == nick_estoque.lower()), None)

    if not conta_encontrada:
        await interaction.followup.send(f"❌ Conta `{nick_estoque}` não encontrada.", ephemeral=True)
        return

    if not conta_encontrada.get("brainrots"):
        await interaction.followup.send(f"ℹ️ A conta `{nick_estoque}` não possui itens para remover.", ephemeral=True)
        return
    
    view = RemoveItemView(nick_estoque=nick_estoque, items=conta_encontrada["brainrots"])
    await interaction.followup.send("Selecione o item que deseja remover:", view=view, ephemeral=True)

# --- Comandos do Grupo /search ---

@search_group.command(name="contas", description="Abre uma interface para buscar itens nas contas.")
async def search_contas(interaction: discord.Interaction):
    view = SearchView()
    await interaction.response.send_message("Use os filtros abaixo para buscar no estoque:", view=view, ephemeral=True)





# --- Registro dos novos grupos no bot ---
client.tree.add_command(add_group)
client.tree.add_command(remove_group)
client.tree.add_command(search_group)
client.tree.add_command(config_group)

# --- Execução do Bot ---
if __name__ == "__main__":
    carregar_configs_globais()
    token = CONFIG_DATA.get("ACCOUNT_MANAGER_BOT_TOKEN")
    if token:
        client.run(token)
    else:
        print("ERRO: Token 'ACCOUNT_MANAGER_BOT_TOKEN' não encontrado em config.json.") 