import { Icon } from './Icon'
import { useLang } from '../i18n'

interface Props {
  onOpenHistoryDrawer?: () => void
  onOpenSourcesDrawer?: () => void
}

/** Top header — faithful port of mockup #5 (Modern Glass). */
export function TopNav({ onOpenHistoryDrawer, onOpenSourcesDrawer }: Props) {
  const { t, lang, toggle } = useLang()

  return (
    <header className="h-[70px] flex items-center justify-between px-4 md:px-8 shrink-0 z-40">
      {/* Right (RTL): logo + brand */}
      <div className="flex items-center gap-3">
        {onOpenHistoryDrawer && (
          <button
            onClick={onOpenHistoryDrawer}
            className="p-1.5 -ms-1 rounded-xl text-text-muted hover:text-primary md:hidden cursor-pointer"
            title={lang === 'he' ? 'היסטוריית שיחות' : 'Chat History'}
          >
            <Icon name="menu" size={22} />
          </button>
        )}
        <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-glass">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-primary">{t('appName')}</h1>
      </div>

      {/* Left (RTL): controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={toggle}
          className="px-4 py-2 rounded-full glass text-text-main text-sm font-semibold hover:opacity-90 transition cursor-pointer"
          title="HE / EN"
        >
          {lang === 'he' ? 'עברית · EN' : 'EN · עברית'}
        </button>

        {onOpenSourcesDrawer && (
          <button
            onClick={onOpenSourcesDrawer}
            className="h-10 w-10 rounded-full glass grid place-items-center text-accent lg:hidden cursor-pointer"
            title={t('relatedSources')}
          >
            <Icon name="auto_stories" size={18} />
          </button>
        )}

        <button
          className="h-10 w-10 rounded-full glass grid place-items-center text-text-muted hover:text-primary transition cursor-pointer"
          title={t('settings')}
        >
          <Icon name="settings" size={20} />
        </button>

        <div className="h-10 w-10 rounded-full grad grid place-items-center text-white font-bold shrink-0">
          א
        </div>
      </div>
    </header>
  )
}
