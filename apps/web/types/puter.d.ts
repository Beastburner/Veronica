export {};

declare global {
  interface Window {
    puter?: {
      ai?: {
        txt2speech: (
          text: string,
          options?: {
            provider?: string;
            voice?: string;
            model?: string;
            instructions?: string;
          }
        ) => Promise<HTMLAudioElement>;
      };
    };
  }
}
