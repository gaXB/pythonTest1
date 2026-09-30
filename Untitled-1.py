import msvcrt


def add(a: float, b: float) -> float:
	"""Return the sum of two numbers."""
	return a + b


if __name__ == "__main__":
	first = float(input("请输入第一个数: "))
	second = float(input("请输入第二个数: "))
	abc = first+second;
	print(f"两数之和为: {add(first, second)}")
	print(f"两数之和方法2为: {abc}")
	print("Press any key to exit...")
	msvcrt.getch()
