import argparse

def main():
    parser = argparse.ArgumentParser(description="Passing argument sample for port and model_key")
    parser.add_argument('--port', '-p', type=int, default=5001, help='Port number (default: 5001)')
    parser.add_argument('--model_key', '-m', type=str, help='model key')
    parser.add_argument('--foo', required=True, help='show you required option')

    args = parser.parse_args()

    print(f"Port: {args.port}")
    print(f"Model Key: {args.model_key}")
    print(f"Foo: {args.foo}")

    if args.model_key == None:
        print("model_key is not defind in arguments")

if __name__ == '__main__':
    main()