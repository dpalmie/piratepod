import { Store } from "@tanstack/store";

export interface UIState {
  urlDraft: string;
  selectedEpisodeId?: string;
  autoplayEpisodeId?: string;
  expandedJobSections: Record<string, boolean>;
}

export const uiStore = new Store<UIState>({
  urlDraft: "",
  selectedEpisodeId: undefined,
  autoplayEpisodeId: undefined,
  expandedJobSections: {},
});

export const uiActions = {
  setUrlDraft(urlDraft: string) {
    uiStore.setState((state) => ({ ...state, urlDraft }));
  },
  clearCreateForm() {
    uiStore.setState((state) => ({ ...state, urlDraft: "" }));
  },
  selectEpisode(selectedEpisodeId: string) {
    uiStore.setState((state) => ({
      ...state,
      selectedEpisodeId,
      autoplayEpisodeId: undefined,
    }));
  },
  playEpisode(episodeId: string) {
    uiStore.setState((state) => ({
      ...state,
      selectedEpisodeId: episodeId,
      autoplayEpisodeId: episodeId,
    }));
  },
  collapseEpisode() {
    uiStore.setState((state) => ({
      ...state,
      selectedEpisodeId: undefined,
      autoplayEpisodeId: undefined,
    }));
  },
  toggleJobSection(section: string) {
    uiStore.setState((state) => ({
      ...state,
      expandedJobSections: {
        ...state.expandedJobSections,
        [section]: !state.expandedJobSections[section],
      },
    }));
  },
};
