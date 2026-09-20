import Link from "next/link";

export function Nav() {
  return (
    <header className="nav wrap">
      <Link className="brand" href="/">
        <b>IB CUP</b>
        <span>DUBAI TIME</span>
      </Link>
      <nav className="nav-links">
        <Link href="/rating">Рейтинг</Link>
        <Link href="/rules">Правила</Link>
        <Link href="/archive">Архив</Link>
        <Link href="/register" className="cta">
          Регистрация
        </Link>
      </nav>
    </header>
  );
}
