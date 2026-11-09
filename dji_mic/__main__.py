import sys


def main() -> None:
    if "--classic" in sys.argv:
        sys.argv.remove("--classic")
        from .ui import main as classic_main

        classic_main()
    else:
        from .webui import main as web_main

        web_main()


if __name__ == "__main__":
    main()
