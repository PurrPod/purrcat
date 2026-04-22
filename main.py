# main.py
import asyncio
import typer
from rich.console import Console

app = typer.Typer(help="Cat-in-Cup Command Line Interface & TUI Launcher")
console = Console()

@app.command()
def start(
    port: int = typer.Option(8000, help="Port to run the backend API server"),
    host: str = typer.Option("127.0.0.1", help="Host address")
):
    """
    启动纯后端服务 (类似原本的 backend.py)
    """
    console.print(f"[green]Starting Cat-in-Cup backend on {host}:{port}...[/green]")
    import uvicorn
    # 假设你的 FastAPI app 实例在 backend.py 或 src/api/app.py 中
    try:
        from backend import app as fastapi_app 
        uvicorn.run(fastapi_app, host=host, port=port)
    except ImportError:
        console.print("[red]Error: backend.py not found. Please check your setup.[/red]")

@app.command()
def tui():
    """
    启动终端图形界面 (TUI)
    """
    console.print("[yellow]Initializing Textual UI...[/yellow]")
    from tui.app import CatInCupApp
    
    # 启动 Textual App
    tui_app = CatInCupApp()
    tui_app.run()

@app.command()
def chat(message: str):
    """
    CLI 单次对话模式：不启动 UI，直接和 Agent 对话
    """
    console.print(f"[bold blue]You:[/bold blue] {message}")
    # 这里调用你的 src/agent 逻辑
    try:
        from src.agent.agent import chat_with_agent
        
        response = asyncio.run(chat_with_agent(message))
        console.print(f"[bold magenta]Cat-in-Cup:[/bold magenta] {response}")
    except ImportError:
        console.print("[red]Error: src/agent/agent.py not found. Please check your setup.[/red]")

if __name__ == "__main__":
    app()