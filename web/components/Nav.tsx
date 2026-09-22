import Link from "next/link";

export function Nav() {
  return (
    <header className="nav wrap">
      <Link className="brand" href="/">
        <b>CHAMP</b>
        <span>UTC+2</span>
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
